"""Decode raw sensor images with explicit encoding and row stride."""
import base64
import numpy as np


def image_array(data, width, height, encoding, step=None, *, grayscale=False):
    import cv2
    width, height = int(width), int(height)
    if width <= 0 or height <= 0:
        raise ValueError('image dimensions must be positive')
    encoding = encoding.lower()
    encoding = {'8uc1': 'mono8', 'yuv422_yuy2': 'yuyv', 'yuyv422': 'yuyv',
                'yuv422': 'uyvy'}.get(encoding, encoding)
    bpp = {'mono8': 1, 'yuyv': 2, 'uyvy': 2, 'rgb8': 3, 'bgr8': 3, 'nv12': 1}.get(encoding)
    if bpp is None:
        raise ValueError(f'unsupported image encoding: {encoding}')
    stride = width * bpp if step is None else int(step)
    if stride < width * bpp:
        raise ValueError('image row stride is smaller than the pixel data')
    if encoding in ('yuyv', 'uyvy', 'nv12') and width % 2:
        raise ValueError('YUV image width must be even')
    if encoding == 'nv12' and height % 2:
        raise ValueError('NV12 image height must be even')
    rows = height * 3 // 2 if encoding == 'nv12' else height
    if isinstance(data, str):
        data = base64.b64decode(data, validate=True)
    data = bytes(data)
    if len(data) != stride * rows:
        raise ValueError(f'image length mismatch: expected {stride * rows}, got {len(data)}')
    packed = np.frombuffer(data, np.uint8).reshape(rows, stride)[:, :width * bpp].copy()
    if encoding == 'mono8':
        return packed
    if encoding == 'nv12':
        if grayscale:
            return packed[:height].copy()
        return cv2.cvtColor(packed, cv2.COLOR_YUV2BGR_NV12)
    packed = packed.reshape(height, width, bpp)
    if grayscale and encoding in ('yuyv', 'uyvy'):
        return packed[:, :, 0 if encoding == 'yuyv' else 1].copy()
    if encoding == 'bgr8':
        return cv2.cvtColor(packed, cv2.COLOR_BGR2GRAY) if grayscale else packed
    conversion = {'rgb8': cv2.COLOR_RGB2BGR, 'yuyv': cv2.COLOR_YUV2BGR_YUYV,
                  'uyvy': cv2.COLOR_YUV2BGR_UYVY}[encoding]
    result = cv2.cvtColor(packed, conversion)
    return cv2.cvtColor(result, cv2.COLOR_BGR2GRAY) if grayscale else result


def raw_image(data, *, grayscale=False):
    required = ('data', 'width', 'height', 'encoding')
    if not all(key in data for key in required):
        raise ValueError('message is not a supported RawImage/Image')
    return image_array(data['data'], data['width'], data['height'], data['encoding'],
                       data.get('step', data.get('stride')), grayscale=grayscale)


def save_image(path, image):
    import cv2
    from pathlib import Path
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    if not cv2.imwrite(str(path), image):
        raise OSError(f'failed to write image: {path}')
