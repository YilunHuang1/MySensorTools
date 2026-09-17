from pathlib import Path
import importlib.util
import numpy as np
import pytest
import yaml

from sensor_tools.calibration import cameras, stereo
from sensor_tools.images import image_array


def module(path):
    spec = importlib.util.spec_from_file_location(Path(path).stem, Path(__file__).resolve().parents[1] / path)
    result = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result)
    return result


def camera(label, model='radial_tangential', count=4):
    return {'camera': dict(label=label, type='pinhole', image_width=640, image_height=480,
        intrinsics={'data': [300., 301., 320., 240.]}, distortion={'type': model, 'parameters': {'data': [0.] * count}})}


@pytest.mark.parametrize('count', [4, 5, 8])
def test_current_and_legacy_calibration_agree(tmp_path, count):
    new = {'cameras': [camera('stereo_left', count=count), camera('stereo_right', count=count)]}
    old = {'image_width': 640, 'image_height': 480}
    for side in ['left', 'right']:
        old[side + '_camera_matrix'] = {'data': [300., 0, 320., 0, 301., 240., 0, 0, 1.]}
        old[side + '_distortion_coefficients'] = {'data': [0.] * count}
    for label, values in cameras(new).items():
        for field in ['K', 'D']:
            np.testing.assert_array_equal(values[field], cameras(old)[label][field])
    path = tmp_path / 'calibration.yaml'
    path.write_text(yaml.safe_dump(new))
    assert stereo(path)[0]['width'] == 640


def test_fisheye_is_not_interpreted_as_radtan():
    parsed = cameras({'cameras': [camera('stereo_left', 'equidistant')]})
    assert parsed['stereo_left']['model'] == 'equidistant'
    with pytest.raises(ValueError, match='coefficient count'):
        cameras({'cameras': [camera('stereo_left', 'equidistant', 8)]})
    with pytest.raises(ValueError, match='unsupported distortion model'):
        cameras({'cameras': [camera('stereo_left', 'fov')]})


def test_luma_is_preserved_not_rescaled():
    np.testing.assert_array_equal(image_array(bytes([0, 128, 255, 128]), 2, 1, 'yuyv', grayscale=True), [[0, 255]])
    np.testing.assert_array_equal(image_array(bytes([16, 235, 40, 70, 128, 128]), 2, 2, 'nv12', grayscale=True), [[16, 235], [40, 70]])


def test_capture_full_is_superset():
    capture = module('camera/capture_stereo_isp.py')
    assert set(capture.selected_topics('isp')) <= set(capture.selected_topics('full'))
    assert set(capture.selected_topics('review')) <= set(capture.selected_topics('isp'))
    assert 'image_right_raw/nv12_half' in capture.selected_topics('full')
    assert 'image_left_raw/nv12' in capture.selected_topics('full')
    assert len(capture.selected_topics('full')) == len(set(capture.selected_topics('full')))


def test_eeprom_rejects_partial_and_marks_inference():
    parser = module('camera/eeprom/parse_eeprom.py')
    with pytest.raises(ValueError, match='truncated'):
        parser.parse_eeprom_data('0x01 0x02')
    with pytest.raises(ValueError, match='complete'):
        parser.parse_eeprom_data('0x01 junk 0x02')
    result = parser.parse_eeprom_data((bytes(40) + b'EXAMPLE123').hex())
    assert result['sn_source'] == 'heuristic_printable_run'
