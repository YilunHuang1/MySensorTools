"""Read legacy OpenCV and current camera-list calibration files."""
from pathlib import Path
import numpy as np
import yaml


class CalibrationLoader(yaml.SafeLoader):
    pass


CalibrationLoader.add_constructor('tag:yaml.org,2002:opencv-matrix',
                                  lambda loader, node: loader.construct_mapping(node, deep=True))


def load(path):
    text = Path(path).read_text(encoding='utf-8')
    if text.startswith('%YAML:'):
        text = text.split('\n', 1)[1]
    result = yaml.load(text, Loader=CalibrationLoader)
    if not isinstance(result, dict):
        raise ValueError('calibration root must be an object')
    return result


def _values(value):
    return value.get('data') if isinstance(value, dict) else value


def _validated(K, D, width, height, model):
    K, D = np.asarray(K, dtype=float).reshape(3, 3), np.asarray(D, dtype=float).ravel()
    width, height = int(width), int(height)
    if width <= 0 or height <= 0 or not np.isfinite(K).all() or not np.isfinite(D).all() or K[0, 0] <= 0 or K[1, 1] <= 0:
        raise ValueError('invalid dimensions or non-finite camera parameters')
    model = {'plumb_bob': 'radial_tangential', 'rational_polynomial': 'radial_tangential', 'fisheye': 'equidistant'}.get(model, model)
    if model == 'none':
        if D.size and np.any(D):
            raise ValueError('nonzero distortion coefficients for model none')
        D, model = np.zeros(4), 'radial_tangential'
    if model not in ('radial_tangential', 'equidistant'):
        raise ValueError(f'unsupported distortion model {model}')
    if (model == 'equidistant' and D.size != 4) or (model == 'radial_tangential' and D.size not in (4, 5, 8)):
        raise ValueError(f'{model}: unsupported coefficient count {D.size}')
    return dict(K=K, D=D, width=width, height=height, model=model)


def cameras(calibration):
    result = {}
    if 'cameras' in calibration:
        for entry in calibration['cameras']:
            camera = entry['camera']
            label = camera['label']
            if label in result:
                raise ValueError(f'duplicate camera label {label}')
            if camera.get('type') != 'pinhole':
                raise ValueError(f"{label}: unsupported camera model {camera.get('type')}")
            fx, fy, cx, cy = _values(camera['intrinsics'])
            distortion = camera['distortion']
            result[label] = _validated([[fx, 0, cx], [0, fy, cy], [0, 0, 1]],
                                       _values(distortion['parameters']), camera['image_width'],
                                       camera['image_height'], distortion['type'])
    else:
        for side in ('left', 'right'):
            result['stereo_' + side] = _validated(_values(calibration[side + '_camera_matrix']),
                _values(calibration[side + '_distortion_coefficients']), calibration['image_width'],
                calibration['image_height'], calibration.get(side + '_distortion_model', calibration.get('distortion_model', 'radial_tangential')))
    if not result:
        raise ValueError('no cameras in calibration')
    return result


def stereo(path):
    parsed = cameras(load(path))
    left, right = parsed['stereo_left'], parsed['stereo_right']
    if (left['width'], left['height']) != (right['width'], right['height']):
        raise ValueError('stereo image dimensions differ')
    return left, right
