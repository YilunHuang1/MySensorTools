"""Statistics for Foxglove PointCloud and ROS PointCloud2, including row padding."""
import base64
import math
import struct


ROS_FORMATS = {1: 'b', 2: 'B', 3: 'h', 4: 'H', 5: 'i', 6: 'I', 7: 'f', 8: 'd'}
FOXGLOVE_FORMATS = {1: 'B', 2: 'b', 3: 'H', 4: 'h', 5: 'I', 6: 'i', 7: 'f', 8: 'd'}


def statistics(message):
    ros = 'point_step' in message
    stride = message.get('point_step' if ros else 'point_stride', 0)
    if not isinstance(stride, int) or stride <= 0:
        raise ValueError('invalid point stride')
    data = message.get('data', b'')
    data = base64.b64decode(data, validate=True) if isinstance(data, str) else bytes(data)
    if ros:
        width, height = message['width'], message['height']
        row_stride = message['row_step']
        if min(width, height) < 0 or row_stride < width * stride or len(data) != height * row_stride:
            raise ValueError('PointCloud2 dimensions/row stride/data length mismatch')
    else:
        if len(data) % stride:
            raise ValueError('PointCloud data length is not a multiple of point_stride')
        width, height, row_stride = len(data) // stride, 1, len(data)
    formats = ROS_FORMATS if ros else FOXGLOVE_FORMATS
    endian = '>' if ros and message.get('is_bigendian') else '<'
    fields = {}
    for field in message.get('fields', []):
        name, offset = field['name'], field['offset']
        code = formats.get(field['datatype' if ros else 'type'])
        count = field.get('count', 1) if ros else 1
        if not code or count < 1 or offset < 0 or offset + struct.calcsize(code) * count > stride or name in fields:
            raise ValueError(f'invalid or duplicate point field: {name}')
        fields[name] = (offset, endian + code, count)
    for name in ['x', 'y', 'z']:
        if name not in fields or fields[name][2] != 1:
            raise ValueError(f'missing scalar field {name}')
    result = dict(total_points=width * height, width=width, height=height, point_step=stride,
                  fields=list(fields), data_length=len(data), valid_points=0, nan_points=0,
                  zero_points=0, min_distance=None, max_distance=None, mean_distance=None)
    distances, intensities, timestamps = [], [], []
    for row in range(height):
        for col in range(width):
            base = row * row_stride + col * stride
            def value(name):
                offset, fmt, _ = fields[name]
                return struct.unpack_from(fmt, data, base + offset)[0]
            xyz = [value(name) for name in ['x', 'y', 'z']]
            if not all(map(math.isfinite, xyz)):
                result['nan_points'] += 1
            else:
                distance = math.sqrt(sum(v * v for v in xyz))
                if distance < 1e-6:
                    result['zero_points'] += 1
                else:
                    distances.append(distance)
                    key = 'intensity' if 'intensity' in fields else 'i' if 'i' in fields else None
                    if key and fields[key][2] == 1 and math.isfinite(value(key)):
                        intensities.append(value(key))
            if 'timestamp' in fields and fields['timestamp'][2] == 1:
                stamp = value('timestamp')
                if not math.isfinite(stamp):
                    raise ValueError('non-finite point timestamp; ordered frame boundaries are unknown')
                timestamps.append(stamp)
    result['valid_points'] = len(distances)
    if distances:
        result.update(min_distance=min(distances), max_distance=max(distances), mean_distance=sum(distances) / len(distances))
    if intensities:
        result.update(min_intensity=min(intensities), max_intensity=max(intensities), mean_intensity=sum(intensities) / len(intensities))
    if timestamps:
        result.update(first_point_timestamp=timestamps[0], last_point_timestamp=timestamps[-1],
                      within_frame_time_regressions=sum(b < a for a, b in zip(timestamps, timestamps[1:])))
    return result
