import hashlib
import sys
from pathlib import Path

import pytest
from PIL import Image, ImageDraw

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from scripts.publish_rabuta_fronts import snapshot_fronts, publish_fronts


def fixture(tmp_path):
    target=tmp_path/'front-v3'; target.mkdir()
    (target/'084909000484-front.jpg').write_bytes(b'old-front')
    (target/'0123456789012-front.jpg').write_bytes(b'untouched-other-front')
    source=tmp_path/'camera.jpg'; Image.new('RGB',(1000,1200),(100,130,20)).save(source)
    mask=tmp_path/'mask.png'
    matte=Image.new('L',(1000,1200),0); ImageDraw.Draw(matte).rectangle((100,100,900,1100),fill=255); matte.save(mask)
    candidate=tmp_path/'candidate.png'
    im=Image.new('RGB',(2400,2400),'white')
    ImageDraw.Draw(im).rectangle((800,200,1600,2200),fill=(50,130,20))
    im.save(candidate)
    digest=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
    record={'excel_row':304,'barcode':'084909000484','record_id':'G1-0303'}
    result={**record,'status':'REPROCESSED_QA_PASS','output_path':str(candidate),'output_sha256':digest(candidate),
            'source_path':str(source),'source_sha256':digest(source),'source_size':[1000,1200],
            'mask_path':str(mask),'mask_sha256':digest(mask),
            'layout':{'source_resolution_warning':False}}
    result['annotation']={**record,'source_path':str(source),'source_sha256':digest(source),'source_size':[1000,1200],
                          'identity_verified':True,'single_product_verified':True,'complete_package':True,
                          'face':'front','evidence':'Reviewed complete authentic front',
                          'polygon':[[100,100],[900,100],[900,1100],[100,1100]]}
    result['qa_pass']=True
    result['qa_evidence']={
        'reviewer':'human_visual',
        'checked_at':'2026-10-15T12:00:00Z',
        'source_sha256':digest(source),
        'mask_sha256':digest(mask),
        'output_sha256':digest(candidate),
        'native_scale_inspected':True,
        'source_mask_inspected':True,
        'source_identity':True,
        'single_complete_front_unit':True,
        'no_neighbor_or_back_face':True,
        'package_edges_and_print_preserved':True,
        'text_readable_at_native_scale':True,
        'background_and_halo_checked':True,
        'no_upscale':True,
    }
    return target,result,[record]


def test_backed_up_jpeg_replacement_keeps_other_files_unchanged(tmp_path):
    target,result,catalog=fixture(tmp_path)
    backup=tmp_path/'backup'
    snapshot_fronts(target,backup)
    report=publish_fronts([result],catalog,target,backup)
    assert report['published_count']==1
    assert report['qa_pass'] is True
    assert (backup/'files/084909000484-front.jpg').read_bytes()==b'old-front'
    assert (target/'0123456789012-front.jpg').read_bytes()==b'untouched-other-front'
    with Image.open(target/'084909000484-front.jpg') as im:
        assert im.format=='JPEG'
        assert im.size==(2400,2400)
        assert im.getpixel((0,0))==(255,255,255)


def test_pending_records_do_not_overwrite_old_images(tmp_path):
    target,result,catalog=fixture(tmp_path)
    snapshot_fronts(target,tmp_path/'backup')
    result['status']='NEEDS_MANUAL_REVIEW'
    report=publish_fronts([result],catalog,target,tmp_path/'backup')
    assert report['published_count']==0
    assert (target/'084909000484-front.jpg').read_bytes()==b'old-front'


def test_review_status_cannot_publish_even_with_qa_fields(tmp_path):
    target,result,catalog=fixture(tmp_path)
    result['status']='REPROCESSED_NEEDS_REVIEW'
    snapshot_fronts(target,tmp_path/'backup')
    report=publish_fronts([result],catalog,target,tmp_path/'backup')
    assert report['published_count']==0
    assert report['skipped'][0]['reason']=='Candidate status is not REPROCESSED_QA_PASS'
    assert (target/'084909000484-front.jpg').read_bytes()==b'old-front'


def test_user_qa_pending_mode_publishes_without_claiming_qa_pass(tmp_path):
    import json
    target,result,catalog=fixture(tmp_path)
    result['status']='REPROCESSED_NEEDS_REVIEW'
    result['layout']['upscale_factor']=0.8
    result.pop('qa_pass')
    result.pop('qa_evidence')
    backup=tmp_path/'backup'
    snapshot_fronts(target,backup)

    report=publish_fronts([result],catalog,target,backup,user_qa_pending=True)

    assert report['published_count']==1
    assert report['qa_pass'] is False
    assert report['user_qa_pending'] is True
    assert report['changes'][0]['status']=='PUBLISHED_PENDING_USER_QA'
    assert report['changes'][0]['qa_pass'] is False
    assert report['changes'][0]['user_qa_required'] is True
    assert json.loads((backup/'publication.json').read_text())['user_qa_pending'] is True
    with Image.open(target/'084909000484-front.jpg') as im:
        assert im.size==(2400,2400)


def test_user_qa_pending_mode_still_rejects_upscaled_candidates(tmp_path):
    target,result,catalog=fixture(tmp_path)
    result['status']='READY_FOR_USER_QA'
    result['layout']['source_resolution_warning']=False
    result['layout']['upscale_factor']=1.01
    backup=tmp_path/'backup'
    snapshot_fronts(target,backup)

    report=publish_fronts([result],catalog,target,backup,user_qa_pending=True)

    assert report['published_count']==0
    assert report['skipped'][0]['reason']=='Candidate requires upscaling'
    assert (target/'084909000484-front.jpg').read_bytes()==b'old-front'


def test_qa_evidence_must_bind_to_exact_source_mask_and_output_hashes(tmp_path):
    target,result,catalog=fixture(tmp_path)
    result['qa_evidence']['output_sha256']='0'*64
    snapshot_fronts(target,tmp_path/'backup')
    report=publish_fronts([result],catalog,target,tmp_path/'backup')
    assert report['published_count']==0
    assert report['skipped'][0]['reason']=='Candidate lacks a complete full-resolution QA pass'
    assert (target/'084909000484-front.jpg').read_bytes()==b'old-front'


def test_candidate_without_explicit_full_resolution_qa_is_not_published(tmp_path):
    target,result,catalog=fixture(tmp_path)
    result.pop('qa_pass')
    result.pop('qa_evidence')
    snapshot_fronts(target,tmp_path/'backup')
    report=publish_fronts([result],catalog,target,tmp_path/'backup')
    assert report['published_count']==0
    assert report['skipped'][0]['reason']=='Candidate lacks a complete full-resolution QA pass'
    assert (target/'084909000484-front.jpg').read_bytes()==b'old-front'


def test_candidate_requiring_upscale_is_skipped(tmp_path):
    target,result,catalog=fixture(tmp_path)
    snapshot_fronts(target,tmp_path/'backup')
    result['layout']['source_resolution_warning']=True
    report=publish_fronts([result],catalog,target,tmp_path/'backup')
    assert report['published_count']==0
    assert report['skipped'][0]['reason']=='Native product resolution would require upscaling'
    assert (target/'084909000484-front.jpg').read_bytes()==b'old-front'


@pytest.mark.parametrize('damage',['source','candidate','mask','identity','collision','changed_target'])
def test_invalid_provenance_or_collision_aborts_before_any_replace(tmp_path,damage):
    target,result,catalog=fixture(tmp_path)
    backup=tmp_path/'backup'; snapshot_fronts(target,backup)
    if damage=='source': Path(result['source_path']).write_bytes(b'changed')
    if damage=='candidate': Path(result['output_path']).write_bytes(b'changed')
    if damage=='mask': Path(result['mask_path']).write_bytes(b'changed')
    if damage=='identity': result['record_id']='WRONG'
    if damage=='collision': catalog.append({**catalog[0],'excel_row':605,'record_id':'OTHER'})
    if damage=='changed_target': (target/'0123456789012-front.jpg').write_bytes(b'user-edit-after-backup')
    before=(target/'084909000484-front.jpg').read_bytes()
    with pytest.raises(ValueError): publish_fronts([result],catalog,target,backup)
    assert (target/'084909000484-front.jpg').read_bytes()==before


def test_duplicate_barcode_publishes_only_explicitly_resolved_record(tmp_path):
    target,result,catalog=fixture(tmp_path)
    conflict={'excel_row':605,'barcode':'084909000484','record_id':'OTHER'}
    catalog.append(conflict)
    resolution={
        '084909000484': {
            'selected': {'excel_row':304,'record_id':'G1-0303'},
            'excluded': [{'excel_row':605,'record_id':'OTHER','reason':'No verified distinct front image'}],
            'evidence':'Selected the complete reviewed front matching the chosen catalog identity.',
        }
    }
    backup=tmp_path/'backup'; snapshot_fronts(target,backup)
    report=publish_fronts([result],catalog,target,backup,identity_resolutions=resolution)
    assert report['published_count']==1
    assert report['changes'][0]['identity_resolution']['selected']['record_id']=='G1-0303'


def test_duplicate_barcode_resolution_must_match_candidate_identity(tmp_path):
    target,result,catalog=fixture(tmp_path)
    catalog.append({'excel_row':605,'barcode':'084909000484','record_id':'OTHER'})
    resolution={
        '084909000484': {
            'selected': {'excel_row':605,'record_id':'OTHER'},
            'excluded': [{'excel_row':304,'record_id':'G1-0303','reason':'Not selected'}],
            'evidence':'Selected another row.',
        }
    }
    snapshot_fronts(target,tmp_path/'backup')
    with pytest.raises(ValueError,match='does not select the candidate identity'):
        publish_fronts([result],catalog,target,tmp_path/'backup',identity_resolutions=resolution)
    assert (target/'084909000484-front.jpg').read_bytes()==b'old-front'


def test_snapshot_is_not_allowed_inside_the_live_directory(tmp_path):
    target,_,_=fixture(tmp_path)
    with pytest.raises(ValueError): snapshot_fronts(target,target/'backup')


def test_interrupted_publish_restores_previous_images(tmp_path,monkeypatch):
    import scripts.publish_rabuta_fronts as pub
    target,result,catalog=fixture(tmp_path)
    second={**result,'excel_row':4,'barcode':'0123456789012','record_id':'SECOND'}
    second['annotation']={**result['annotation'],'excel_row':4,'barcode':'0123456789012','record_id':'SECOND'}
    catalog.append({k:second[k] for k in ('excel_row','barcode','record_id')})
    snapshot_fronts(target,tmp_path/'backup')
    original_replace=pub.os.replace
    count=0
    def fail_second(src,dest):
        nonlocal count
        if Path(src).suffix=='.jpg':
            count+=1
            if count==2: raise OSError('disk write failure')
        return original_replace(src,dest)
    monkeypatch.setattr(pub.os,'replace',fail_second)
    with pytest.raises(OSError): publish_fronts([result,second],catalog,target,tmp_path/'backup')
    assert (target/'084909000484-front.jpg').read_bytes()==b'old-front'
    assert (target/'0123456789012-front.jpg').read_bytes()==b'untouched-other-front'


def test_relabelled_candidate_with_valid_other_identity_cannot_be_published(tmp_path):
    target,result,catalog=fixture(tmp_path)
    other={'excel_row':4,'barcode':'0123456789012','record_id':'SECOND'}
    catalog.append(other)
    result.update(other)
    snapshot_fronts(target,tmp_path/'backup')
    with pytest.raises(ValueError): publish_fronts([result],catalog,target,tmp_path/'backup')
    assert (target/'0123456789012-front.jpg').read_bytes()==b'untouched-other-front'


def test_operator_cancellation_rolls_back_and_does_not_leave_staged_journal(tmp_path,monkeypatch):
    import json
    import scripts.publish_rabuta_fronts as pub
    target,result,catalog=fixture(tmp_path)
    second={**result,'excel_row':4,'barcode':'0123456789012','record_id':'SECOND'}
    second['annotation']={**result['annotation'],'excel_row':4,'barcode':'0123456789012','record_id':'SECOND'}
    catalog.append({k:second[k] for k in ('excel_row','barcode','record_id')})
    backup=tmp_path/'backup'; snapshot_fronts(target,backup)
    original_replace=pub.os.replace
    count=0
    def cancel_second(src,dest):
        nonlocal count
        if Path(src).suffix=='.jpg':
            count+=1
            if count==2: raise KeyboardInterrupt('operator cancelled')
        return original_replace(src,dest)
    monkeypatch.setattr(pub.os,'replace',cancel_second)
    with pytest.raises(KeyboardInterrupt): publish_fronts([result,second],catalog,target,backup)
    assert (target/'084909000484-front.jpg').read_bytes()==b'old-front'
    assert (target/'0123456789012-front.jpg').read_bytes()==b'untouched-other-front'
    assert json.loads((backup/'publication.json').read_text())['status']=='ROLLED_BACK'


def test_cancellation_immediately_after_replace_is_reconciled(tmp_path,monkeypatch):
    import scripts.publish_rabuta_fronts as pub
    target,result,catalog=fixture(tmp_path)
    backup=tmp_path/'backup'; snapshot_fronts(target,backup)
    original_replace=pub.os.replace
    cancelled=False
    def replace_then_cancel(src,dest):
        nonlocal cancelled
        outcome=original_replace(src,dest)
        if Path(src).suffix=='.jpg' and not cancelled:
            cancelled=True
            raise KeyboardInterrupt('cancelled after replace took effect')
        return outcome
    monkeypatch.setattr(pub.os,'replace',replace_then_cancel)
    with pytest.raises(KeyboardInterrupt): publish_fronts([result],catalog,target,backup)
    assert (target/'084909000484-front.jpg').read_bytes()==b'old-front'
    import json
    assert json.loads((backup/'publication.json').read_text())['status']=='ROLLED_BACK'


def test_final_journal_commit_failure_rolls_back_published_image(tmp_path,monkeypatch):
    import scripts.publish_rabuta_fronts as pub
    target,result,catalog=fixture(tmp_path)
    backup=tmp_path/'backup'; snapshot_fronts(target,backup)
    original_replace=pub.os.replace
    journal_commits=0
    def fail_applied_journal(src,dest):
        nonlocal journal_commits
        if Path(dest).name=='publication.json':
            journal_commits+=1
            if journal_commits==2: raise OSError('journal commit failed')
        return original_replace(src,dest)
    monkeypatch.setattr(pub.os,'replace',fail_applied_journal)
    with pytest.raises(OSError): publish_fronts([result],catalog,target,backup)
    assert (target/'084909000484-front.jpg').read_bytes()==b'old-front'
    import json
    assert json.loads((backup/'publication.json').read_text())['status']=='ROLLED_BACK'
