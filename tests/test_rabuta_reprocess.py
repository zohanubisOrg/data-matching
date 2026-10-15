import hashlib
import sys
from pathlib import Path

import pytest
from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from scripts.reprocess_rabuta_verified import run_reprocessing


def data(tmp_path, *, native_resolution=True):
    source = tmp_path/'camera.png'
    size = (2500, 2500) if native_resolution else (1200, 1000)
    Image.new('RGB', size, (245, 240, 220)).save(source)
    record = {'excel_row': 304, 'barcode': '084909000484', 'record_id': 'G1-0303'}
    annotation = {**record, 'source_path': str(source),
                  'source_sha256': hashlib.sha256(source.read_bytes()).hexdigest(),
                  'source_size': list(size), 'face': 'front', 'identity_verified': True,
                  'complete_package': True, 'evidence': 'Verified source and package boundary',
                  'single_product_verified': True,
                  'polygon': ([[100,100],[2400,100],[2400,2400],[100,2400]] if native_resolution
                              else [[100,100],[700,100],[700,800],[100,800]])}
    return record, annotation


def test_real_render_provenance_and_original_source_unchanged(tmp_path):
    record, annotation = data(tmp_path)
    output = tmp_path/'review'
    result = run_reprocessing([record], [annotation], output, tmp_path/'originals')[0]
    assert result['status'] == 'REPROCESSED_NEEDS_REVIEW'
    assert result['barcode'] == '084909000484'
    assert result['source_sha256'] == annotation['source_sha256']
    assert hashlib.sha256(Path(annotation['source_path']).read_bytes()).hexdigest() == annotation['source_sha256']
    assert Image.open(result['output_path']).size == (2400, 2400)
    assert Image.open(result['mask_path']).size == (2500, 2500)
    assert result['layout']['source_resolution_warning'] is False
    assert result['layout']['upscale_factor'] <= 1


def test_rotated_candidate_mask_stays_aligned_with_original_source(tmp_path):
    record, annotation = data(tmp_path)
    annotation['rotation_ccw'] = 90
    result = run_reprocessing([record], [annotation], tmp_path/'review', tmp_path/'originals')[0]
    assert Image.open(result['mask_path']).size == tuple(result['source_size'])
    assert result['layout']['render_source_size'] == [2500,2500]
    assert result['layout']['rotation_ccw'] == 90


def test_reprocessing_blocks_candidate_that_would_need_upscaling(tmp_path):
    record, annotation = data(tmp_path, native_resolution=False)
    result = run_reprocessing([record], [annotation], tmp_path/'review', tmp_path/'originals')[0]
    assert result['status'] == 'BLOCKED_NEEDS_SOURCE'
    assert 'upscal' in result['reason'].lower()
    assert 'output_path' not in result


@pytest.mark.parametrize('damage', ['hash','face','size','identity','film','row','count'])
def test_unverified_annotation_cannot_save_candidate(tmp_path, damage):
    record, annotation = data(tmp_path)
    if damage == 'hash': annotation['source_sha256'] = '0'*64
    if damage == 'face': annotation['face'] = 'back'
    if damage == 'size': annotation['source_size'] = [1200,1000]
    if damage == 'identity': annotation['identity_verified'] = False
    if damage == 'film': annotation['film_matting_required'] = True
    if damage == 'row': annotation['excel_row'] = 305
    if damage == 'count': annotation['single_product_verified'] = False
    result = run_reprocessing([record], [annotation], tmp_path/'review', tmp_path/'originals')[0]
    assert result['status'] in ('NEEDS_MANUAL_REVIEW','BLOCKED_NEEDS_SOURCE')
    assert 'output_path' not in result


def test_barcode_collision_blocks_both_records_even_with_valid_annotation(tmp_path):
    record, annotation = data(tmp_path)
    other = {**record, 'excel_row': 605, 'record_id': 'OTHER'}
    result = run_reprocessing([record,other], [annotation], tmp_path/'review', tmp_path/'originals')
    assert [x['status'] for x in result] == ['BLOCKED_IDENTITY_CONFLICT']*2
    assert not list((tmp_path/'review').glob('*-front.png'))


def test_selected_subset_still_blocks_conflict_in_full_catalog(tmp_path):
    record, annotation = data(tmp_path)
    other = {**record, 'excel_row': 605, 'record_id': 'OTHER'}
    result = run_reprocessing([record], [annotation], tmp_path/'review', tmp_path/'originals',
                             catalog_records=[record,other])
    assert result[0]['status'] == 'BLOCKED_IDENTITY_CONFLICT'


def test_explicit_barcode_resolution_allows_only_the_selected_annotated_record(tmp_path):
    record, annotation = data(tmp_path)
    other = {**record, 'excel_row': 605, 'record_id': 'OTHER'}
    resolution = {
        record['barcode']: {
            'selected': {'excel_row': record['excel_row'], 'record_id': record['record_id']},
            'excluded': [{'excel_row': other['excel_row'], 'record_id': other['record_id'],
                          'reason': 'No validated front for this conflicting identity'}],
            'evidence': 'The selected source front matches the product name and complete package.',
        }
    }
    result = run_reprocessing([record, other], [annotation], tmp_path/'review', tmp_path/'originals',
                              catalog_records=[record, other], identity_resolutions=resolution)
    assert result[0]['status'] == 'REPROCESSED_NEEDS_REVIEW'
    assert result[1]['status'] == 'BLOCKED_IDENTITY_CONFLICT'


def test_no_source_and_no_annotation_is_blocked(tmp_path):
    record, _ = data(tmp_path)
    result = run_reprocessing([record], [], tmp_path/'review', tmp_path/'originals')[0]
    assert result['status'] == 'BLOCKED_NEEDS_SOURCE'


def test_blocked_record_does_not_retain_stale_output_provenance(tmp_path):
    record, _ = data(tmp_path)
    record.update(output_path='old/front.png', output_sha256='deadbeef',
                  mask_path='old/mask.png', mask_sha256='deadbeef',
                  overlay_path='old/overlay.jpg', source_sha256='old-source-hash',
                  annotation={'face':'front'}, layout={'upscale_factor':0.5})
    result = run_reprocessing([record], [], tmp_path/'review', tmp_path/'originals')[0]
    assert result['status'] == 'BLOCKED_NEEDS_SOURCE'
    assert not any(name in result for name in
                   ('output_path','output_sha256','mask_path','mask_sha256','overlay_path','annotation','layout'))


def test_existing_source_is_only_a_candidate_not_an_automatic_front(tmp_path):
    record, _ = data(tmp_path)
    originals = tmp_path/'originals'
    folder = originals/record['barcode']
    folder.mkdir(parents=True)
    Image.new('RGB',(1200,1000)).save(folder/'camera.jpg')
    result = run_reprocessing([record], [], tmp_path/'review', originals)[0]
    assert result['status'] == 'NEEDS_MANUAL_REVIEW'
    assert len(result['source_candidates']) == 1


def test_source_map_only_proposes_native_sources_and_never_old_cutouts(tmp_path):
    record, annotation = data(tmp_path)
    source_map = {record['barcode']: {'paths': [annotation['source_path'], str(tmp_path/'front-v3/old.jpg')]}}
    result = run_reprocessing([record], [], tmp_path/'review', tmp_path/'originals', source_map)[0]
    assert result['status'] == 'NEEDS_MANUAL_REVIEW'
    assert result['source_candidates'] == [annotation['source_path']]


def test_old_delivery_directory_and_existing_run_are_never_overwritten(tmp_path):
    record, annotation = data(tmp_path)
    with pytest.raises(ValueError):
        run_reprocessing([record], [annotation], tmp_path/'front-v3', tmp_path/'originals')
    output = tmp_path/'review'
    run_reprocessing([record], [annotation], output, tmp_path/'originals')
    with pytest.raises(FileExistsError):
        run_reprocessing([record], [annotation], output, tmp_path/'originals')
