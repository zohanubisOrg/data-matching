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
    source=tmp_path/'camera.jpg'; source.write_bytes(b'authentic-source-file')
    mask=tmp_path/'mask.png'; mask.write_bytes(b'verified-mask')
    candidate=tmp_path/'candidate.png'
    im=Image.new('RGB',(2400,2400),'white')
    ImageDraw.Draw(im).rectangle((800,200,1600,2200),fill=(50,130,20))
    im.save(candidate)
    digest=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
    record={'excel_row':304,'barcode':'084909000484','record_id':'G1-0303'}
    result={**record,'status':'REPROCESSED_NEEDS_REVIEW','output_path':str(candidate),'output_sha256':digest(candidate),
            'source_path':str(source),'source_sha256':digest(source),'mask_path':str(mask),'mask_sha256':digest(mask)}
    return target,result,[record]


def test_backed_up_jpeg_replacement_keeps_other_files_unchanged(tmp_path):
    target,result,catalog=fixture(tmp_path)
    backup=tmp_path/'backup'
    snapshot_fronts(target,backup)
    report=publish_fronts([result],catalog,target,backup)
    assert report['published_count']==1
    assert report['qa_pass'] is False
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


def test_snapshot_is_not_allowed_inside_the_live_directory(tmp_path):
    target,_,_=fixture(tmp_path)
    with pytest.raises(ValueError): snapshot_fronts(target,target/'backup')


def test_interrupted_publish_restores_previous_images(tmp_path,monkeypatch):
    import scripts.publish_rabuta_fronts as pub
    target,result,catalog=fixture(tmp_path)
    second={**result,'excel_row':4,'barcode':'0123456789012','record_id':'SECOND'}
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
