"""Apply identity-bound rendered fronts under the user's overwrite authorization.

Snapshots every existing file, checks provenance, stages JPEGs, then replaces
individual files atomically. Pending/blocked records keep their current photos.
"""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
import shutil
import sys
import uuid

import numpy as np
from PIL import Image

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from scripts.reprocess_rabuta_verified import key, open_source, read_jsonl, sha256
from product_mapper.vision.package_packshot import mask_from_polygon


def snapshot_fronts(target_dir, backup_dir):
    target,backup=Path(target_dir).resolve(),Path(backup_dir).resolve()
    if not target.is_dir() or backup==target or target in backup.parents or backup in target.parents:
        raise ValueError('Snapshot must be separate from existing live fronts')
    files=sorted(target.iterdir())
    if any(not p.is_file() or p.is_symlink() or p.resolve().parent!=target for p in files):
        raise ValueError('Live fronts must contain only local regular files')
    backup.mkdir(parents=True,exist_ok=False)
    (backup/'files').mkdir()
    entries=[]
    for file in files:
        digest=sha256(file)
        destination=backup/'files'/file.name
        shutil.copy2(file,destination)
        if sha256(destination)!=digest or sha256(file)!=digest:
            raise ValueError(f'Snapshot verification failed: {file.name}')
        entries.append({'name':file.name,'sha256':digest,'bytes':file.stat().st_size})
    manifest={'target_dir':str(target),'created_at':datetime.now(timezone.utc).isoformat(),'files':entries}
    (backup/'snapshot.json').write_text(json.dumps(manifest,indent=2),encoding='utf-8')
    return manifest


def validate_canvas(path):
    with Image.open(path) as image:
        if image.size!=(2400,2400): raise ValueError('Candidate must be 2400 x 2400')
        arr=np.asarray(image.convert('RGB'))
        if not all((edge==255).all() for edge in (arr[0],arr[-1],arr[:,0],arr[:,-1])):
            raise ValueError('Candidate outer border is not pure white')
        if not np.any(arr!=255): raise ValueError('Candidate is blank')


def write_journal(path, report):
    temporary=path.with_name(f'.{path.name}.{uuid.uuid4().hex}.tmp')
    try:
        with temporary.open('w',encoding='utf-8') as stream:
            json.dump(report,stream,ensure_ascii=False,indent=2)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary,path)
    finally:
        if temporary.exists(): temporary.unlink()


def publish_fronts(results,catalog_records,target_dir,backup_dir,identity_resolutions=None,
                   user_qa_pending=False):
    target,backup=Path(target_dir).resolve(),Path(backup_dir).resolve()
    manifest=json.loads((backup/'snapshot.json').read_text(encoding='utf-8'))
    if Path(manifest['target_dir']).resolve()!=target: raise ValueError('Snapshot belongs to a different target')
    before={item['name']:item['sha256'] for item in manifest['files']}
    current={p.name:sha256(p) for p in target.iterdir() if p.is_file()}
    if current!=before: raise ValueError('Live files changed after snapshot; abort to preserve edits')
    for name,digest in before.items():
        if sha256(backup/'files'/name)!=digest: raise ValueError('Snapshot backup has changed')
    identities=defaultdict(set)
    catalog_by_barcode=defaultdict(set)
    catalog={key(r) for r in catalog_records}
    for r in catalog_records:
        if r['barcode']:
            barcode=str(r['barcode'])
            identities[barcode].add(str(r['record_id']))
            catalog_by_barcode[barcode].add((int(r['excel_row']),str(r['record_id'])))
    identity_resolutions=identity_resolutions or {}
    selected=[]; skipped=[]; names=set()
    for result in results:
        layout=result.get('layout',{})
        if (layout.get('source_resolution_warning') is not False):
            skipped.append({'excel_row':result['excel_row'],'barcode':result['barcode'],
                            'record_id':result['record_id'],'status':'NEEDS_MANUAL_REVIEW',
                            'reason':'Native product resolution would require upscaling'})
            continue
        if user_qa_pending:
            try:
                scale=float(layout.get('upscale_factor'))
            except (TypeError,ValueError):
                scale=float('inf')
            if scale>1.0:
                skipped.append({'excel_row':result['excel_row'],'barcode':result['barcode'],
                                'record_id':result['record_id'],'status':'NEEDS_MANUAL_REVIEW',
                                'reason':'Candidate requires upscaling'})
                continue
            accepted_statuses={'READY_FOR_USER_QA','REPROCESSED_NEEDS_REVIEW','REPROCESSED_QA_PASS'}
        else:
            accepted_statuses={'REPROCESSED_QA_PASS'}
        if result['status'] not in accepted_statuses:
            skipped.append({'excel_row':result['excel_row'],'barcode':result['barcode'],
                            'record_id':result['record_id'],'status':result['status'],
                            'reason':'Candidate status is not REPROCESSED_QA_PASS'})
            continue
        qa=result.get('qa_evidence')
        qa_checks=(
            'native_scale_inspected','source_mask_inspected','source_identity',
            'single_complete_front_unit','no_neighbor_or_back_face',
            'package_edges_and_print_preserved','text_readable_at_native_scale',
            'background_and_halo_checked','no_upscale',
        )
        has_valid_qa=(result.get('qa_pass') is True and isinstance(qa,dict)
            and bool(str(qa.get('reviewer','')).strip())
            and bool(str(qa.get('checked_at','')).strip())
            and all(qa.get(check) is True for check in qa_checks)
            and qa.get('source_sha256')==result.get('source_sha256')
            and qa.get('mask_sha256')==result.get('mask_sha256')
            and qa.get('output_sha256')==result.get('output_sha256'))
        if not user_qa_pending and not has_valid_qa:
            skipped.append({'excel_row':result['excel_row'],'barcode':result['barcode'],
                            'record_id':result['record_id'],'status':'NEEDS_MANUAL_REVIEW',
                            'reason':'Candidate lacks a complete full-resolution QA pass'})
            continue
        bc,rid,row=key(result)
        if key(result) not in catalog or not re.fullmatch(r'[0-9]{6,20}',bc):
            raise ValueError('Rendered record does not match authoritative catalog identity')
        annotation=result.get('annotation')
        if not isinstance(annotation,dict) or key(annotation)!=key(result):
            raise ValueError('Rendered annotation identity does not match its result identity')
        if (annotation.get('identity_verified') is not True or annotation.get('face')!='front'
            or annotation.get('single_product_verified') is not True
            or annotation.get('complete_package') is not True
            or not isinstance(annotation.get('evidence'),str) or not annotation['evidence'].strip()
            or annotation.get('film_matting_required')):
            raise ValueError('Reviewed annotation does not meet the source/front/package gates')
        if (Path(annotation.get('source_path','')).resolve()!=Path(result.get('source_path','')).resolve()
            or annotation.get('source_sha256')!=result.get('source_sha256')
            or annotation.get('source_size')!=result.get('source_size')):
            raise ValueError('Result source provenance differs from its reviewed annotation')
        identity_resolution=None
        if len(identities[bc])>1:
            identity_resolution=identity_resolutions.get(bc)
            if not isinstance(identity_resolution,dict):
                raise ValueError('Barcode identity collision blocks publication')
            selected_identity=identity_resolution.get('selected')
            selected_key=(int(selected_identity.get('excel_row',-1)),str(selected_identity.get('record_id',''))) if isinstance(selected_identity,dict) else None
            if selected_key!=(row,rid):
                raise ValueError('Barcode resolution does not select the candidate identity')
            if not str(identity_resolution.get('evidence','')).strip():
                raise ValueError('Barcode resolution requires evidence')
            excluded=identity_resolution.get('excluded')
            if not isinstance(excluded,list):
                raise ValueError('Barcode resolution requires excluded identities and reasons')
            excluded_keys=set()
            for item in excluded:
                if not isinstance(item,dict) or not str(item.get('reason','')).strip():
                    raise ValueError('Every excluded barcode identity requires a reason')
                excluded_keys.add((int(item.get('excel_row',-1)),str(item.get('record_id',''))))
            expected_excluded=catalog_by_barcode[bc]-{selected_key}
            if excluded_keys!=expected_excluded:
                raise ValueError('Barcode resolution does not account for every conflicting catalog identity')
        name=f'{bc}-front.jpg'
        if name in names: raise ValueError('Multiple candidates target the same barcode filename')
        names.add(name)
        for path_field,hash_field in (('source_path','source_sha256'),('output_path','output_sha256'),('mask_path','mask_sha256')):
            if sha256(result[path_field])!=result[hash_field]: raise ValueError(f'Provenance changed: {path_field}')
        source=open_source(result['source_path'])
        if list(source.size)!=annotation['source_size']:
            raise ValueError('EXIF-oriented source dimensions differ from reviewed annotation')
        expected_mask=mask_from_polygon(source.size,annotation['polygon'])
        with Image.open(result['mask_path']) as mask_image:
            mask=np.asarray(mask_image.convert('L'))
        if mask.shape!=expected_mask.shape or not np.isin(mask,[0,255]).all() or not np.array_equal(mask,expected_mask):
            raise ValueError('Rendered mask differs from the reviewed package polygon')
        validate_canvas(result['output_path'])
        selected.append((name,result))
    staging=backup/f'staging-{uuid.uuid4().hex}'
    staging.mkdir()
    changes=[]
    for name,result in selected:
        staged=staging/name
        with Image.open(result['output_path']) as image:
            image.convert('RGB').save(staged,'JPEG',quality=95,subsampling=0,optimize=True)
        validate_canvas(staged)
        changes.append({'name':name,'excel_row':result['excel_row'],'record_id':result['record_id'],
                        'barcode':result['barcode'],'old_sha256':before.get(name),
                        'new_sha256':sha256(staged),'candidate_sha256':result['output_sha256'],
                        'source_sha256':result['source_sha256'],'mask_sha256':result['mask_sha256'],
                        'status':'PUBLISHED_PENDING_USER_QA' if user_qa_pending else 'PUBLISHED_UNDER_USER_AUTHORIZATION',
                        'qa_pass':False if user_qa_pending else True,
                        'user_qa_required':bool(user_qa_pending),
                        'identity_resolution':identity_resolution})
    journal=backup/'publication.json'
    report={'status':'STAGED','target_dir':str(target),'backup_dir':str(backup),
            'created_at':datetime.now(timezone.utc).isoformat(),'changes':changes,
            'published_count':0,'skipped_count':len(skipped),'skipped':skipped,
            'qa_pass':bool(selected) and not user_qa_pending,
            'user_qa_pending':bool(user_qa_pending)}
    write_journal(journal,report)
    attempted=[]
    try:
        # Recheck immediately before mutation: rendering may take time.
        if {p.name:sha256(p) for p in target.iterdir() if p.is_file()}!=before:
            raise ValueError('Live files changed while staging')
        for change in changes:
            name=change['name']
            attempted.append(name)
            os.replace(staging/name,target/name)
            if sha256(target/name)!=change['new_sha256']: raise ValueError('Replacement verification failed')
        after={p.name:sha256(p) for p in target.iterdir() if p.is_file()}
        expected={**before,**{c['name']:c['new_sha256'] for c in changes}}
        if after!=expected: raise ValueError('Unexpected change outside the publication set')
        report.update(status='APPLIED',published_count=len(attempted),file_count_after=len(after))
        write_journal(journal,report)
    except BaseException as publication_error:
        rollback_errors=[]
        for name in reversed(attempted):
            destination=target/name
            try:
                new_hash=next(c['new_sha256'] for c in changes if c['name']==name)
                current_hash=sha256(destination) if destination.exists() else None
                old_hash=before.get(name)
                # A replace may raise after taking effect, or before it takes effect.
                if current_hash==old_hash:
                    continue
                # Never overwrite an edit made after our replacement.
                if current_hash!=new_hash:
                    raise ValueError(f'Live file changed during rollback: {name}')
                if name in before:
                    restored=staging/f'{name}.restore'
                    shutil.copy2(backup/'files'/name,restored)
                    os.replace(restored,destination)
                    if sha256(destination)!=before[name]:
                        raise ValueError(f'Restored file failed hash verification: {name}')
                else:
                    destination.unlink()
                    if destination.exists(): raise ValueError(f'Could not remove newly published file: {name}')
            except BaseException as rollback_error:
                rollback_errors.append({'name':name,'error':f'{type(rollback_error).__name__}: {rollback_error}'})
        report.update(status='PARTIAL_ROLLBACK_FAILED' if rollback_errors else 'ROLLED_BACK',
                      published_count=0,rollback_errors=rollback_errors)
        try:
            write_journal(journal,report)
        except BaseException as journal_error:
            publication_error.add_note(f'Could not persist rollback journal: {type(journal_error).__name__}: {journal_error}')
        raise
    return report


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--results',type=Path,required=True)
    parser.add_argument('--backup-dir',type=Path,required=True)
    parser.add_argument('--target-dir',type=Path,default=ROOT/'output/catalog_pairs/tagged/front-v3')
    parser.add_argument('--workbook',type=Path,default=ROOT/'output/catalog_pairs/Rabuta_master_final_Delivery_Embedded.xlsx')
    parser.add_argument('--identity-resolutions',type=Path,
                        help='JSONL evidence resolving duplicate barcode output identities')
    parser.add_argument('--apply',action='store_true',help='Apply the overwrite already authorized by the user')
    parser.add_argument('--user-qa-pending',action='store_true',
                        help='Publish provenance-validated candidates for the user to QA; do not claim a QA pass')
    args=parser.parse_args()
    if not args.apply: parser.error('Pass --apply to perform the authorized overwrite')
    import openpyxl
    workbook_hash=sha256(args.workbook)
    workbook=openpyxl.load_workbook(args.workbook,read_only=True,data_only=True)
    catalog=[{'excel_row':row,'barcode':str(values[0] or '').strip(),'record_id':str(values[4] or '').strip()}
             for row,values in enumerate(workbook.active.iter_rows(min_row=4,max_col=5,values_only=True),4)]
    workbook.close()
    if not (args.backup_dir/'snapshot.json').exists(): snapshot_fronts(args.target_dir,args.backup_dir)
    resolutions={}
    if args.identity_resolutions:
        for item in read_jsonl(args.identity_resolutions):
            barcode=str(item.get('barcode','')).strip()
            if not barcode or barcode in resolutions:
                raise ValueError('Duplicate barcode resolution entry or missing barcode')
            resolutions[barcode]=item
    report=publish_fronts(read_jsonl(args.results),catalog,args.target_dir,args.backup_dir,
                          identity_resolutions=resolutions,user_qa_pending=args.user_qa_pending)
    if sha256(args.workbook)!=workbook_hash: raise ValueError('Workbook changed during publication')
    print(json.dumps({k:report[k] for k in ('status','published_count','skipped_count','backup_dir')}))
    return 0


if __name__=='__main__':
    raise SystemExit(main())
