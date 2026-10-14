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
from scripts.reprocess_rabuta_verified import key, read_jsonl, sha256


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


def publish_fronts(results,catalog_records,target_dir,backup_dir):
    target,backup=Path(target_dir).resolve(),Path(backup_dir).resolve()
    manifest=json.loads((backup/'snapshot.json').read_text(encoding='utf-8'))
    if Path(manifest['target_dir']).resolve()!=target: raise ValueError('Snapshot belongs to a different target')
    before={item['name']:item['sha256'] for item in manifest['files']}
    current={p.name:sha256(p) for p in target.iterdir() if p.is_file()}
    if current!=before: raise ValueError('Live files changed after snapshot; abort to preserve edits')
    for name,digest in before.items():
        if sha256(backup/'files'/name)!=digest: raise ValueError('Snapshot backup has changed')
    identities=defaultdict(set)
    catalog={key(r) for r in catalog_records}
    for r in catalog_records:
        if r['barcode']: identities[str(r['barcode'])].add(str(r['record_id']))
    selected=[]; skipped=[]; names=set()
    for result in results:
        if result['status']!='REPROCESSED_NEEDS_REVIEW':
            skipped.append({'excel_row':result['excel_row'],'barcode':result['barcode'],
                            'record_id':result['record_id'],'status':result['status'],
                            'reason':result.get('reason','Pending source/boundary review')})
            continue
        bc,rid,row=key(result)
        if key(result) not in catalog or not re.fullmatch(r'[0-9]{6,20}',bc):
            raise ValueError('Rendered record does not match authoritative catalog identity')
        if len(identities[bc])>1: raise ValueError('Barcode identity collision blocks publication')
        name=f'{bc}-front.jpg'
        if name in names: raise ValueError('Multiple candidates target the same barcode filename')
        names.add(name)
        for path_field,hash_field in (('source_path','source_sha256'),('output_path','output_sha256'),('mask_path','mask_sha256')):
            if sha256(result[path_field])!=result[hash_field]: raise ValueError(f'Provenance changed: {path_field}')
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
                        'status':'PUBLISHED_UNDER_USER_AUTHORIZATION','qa_pass':False})
    journal=backup/'publication.json'
    report={'status':'STAGED','target_dir':str(target),'backup_dir':str(backup),
            'created_at':datetime.now(timezone.utc).isoformat(),'changes':changes,
            'published_count':0,'skipped_count':len(skipped),'skipped':skipped,'qa_pass':False}
    journal.write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    applied=[]
    try:
        # Recheck immediately before mutation: rendering may take time.
        if {p.name:sha256(p) for p in target.iterdir() if p.is_file()}!=before:
            raise ValueError('Live files changed while staging')
        for change in changes:
            name=change['name']
            os.replace(staging/name,target/name)
            applied.append(name)
            if sha256(target/name)!=change['new_sha256']: raise ValueError('Replacement verification failed')
        after={p.name:sha256(p) for p in target.iterdir() if p.is_file()}
        expected={**before,**{c['name']:c['new_sha256'] for c in changes}}
        if after!=expected: raise ValueError('Unexpected change outside the publication set')
        report.update(status='APPLIED',published_count=len(applied),file_count_after=len(after))
    except Exception:
        for name in reversed(applied):
            destination=target/name
            if name in before:
                restored=staging/f'{name}.restore'
                shutil.copy2(backup/'files'/name,restored)
                os.replace(restored,destination)
            else:
                destination.unlink()
        report.update(status='ROLLED_BACK',published_count=0)
        journal.write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
        raise
    journal.write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    return report


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--results',type=Path,required=True)
    parser.add_argument('--backup-dir',type=Path,required=True)
    parser.add_argument('--target-dir',type=Path,default=ROOT/'output/catalog_pairs/tagged/front-v3')
    parser.add_argument('--workbook',type=Path,default=ROOT/'output/catalog_pairs/Rabuta_master_final_Delivery_Embedded.xlsx')
    parser.add_argument('--apply',action='store_true',help='Apply the overwrite already authorized by the user')
    args=parser.parse_args()
    if not args.apply: parser.error('Pass --apply to perform the authorized overwrite')
    import openpyxl
    workbook_hash=sha256(args.workbook)
    workbook=openpyxl.load_workbook(args.workbook,read_only=True,data_only=True)
    catalog=[{'excel_row':row,'barcode':str(values[0] or '').strip(),'record_id':str(values[4] or '').strip()}
             for row,values in enumerate(workbook.active.iter_rows(min_row=4,max_col=5,values_only=True),4)]
    workbook.close()
    if not (args.backup_dir/'snapshot.json').exists(): snapshot_fronts(args.target_dir,args.backup_dir)
    report=publish_fronts(read_jsonl(args.results),catalog,args.target_dir,args.backup_dir)
    if sha256(args.workbook)!=workbook_hash: raise ValueError('Workbook changed during publication')
    print(json.dumps({k:report[k] for k in ('status','published_count','skipped_count','backup_dir')}))
    return 0


if __name__=='__main__':
    raise SystemExit(main())
