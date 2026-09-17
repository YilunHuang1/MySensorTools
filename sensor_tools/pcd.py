"""PCD reader driven by FIELDS/SIZE/TYPE/COUNT, for ASCII and binary files."""
from pathlib import Path
import io
import numpy as np


def read_pcd(path):
    header = {}
    with Path(path).open('rb') as stream:
        while True:
            line = stream.readline(65536)
            if not line or len(line) == 65536 or stream.tell() > 1024 * 1024:
                raise ValueError('invalid or missing PCD header')
            parts = line.decode('ascii').strip().split()
            if not parts or parts[0].startswith('#'):
                continue
            header[parts[0].upper()] = parts[1:]
            if parts[0].upper() == 'DATA':
                break
        raw = stream.read()
    try:
        names = header['FIELDS']
        sizes = [int(x) for x in header['SIZE']]
        types = header['TYPE']
        counts = [int(x) for x in header.get('COUNT', ['1'] * len(names))]
        point_count = int(header['POINTS'][0]) if 'POINTS' in header else int(header['WIDTH'][0]) * int(header['HEIGHT'][0])
        mode = header['DATA'][0].lower()
    except (KeyError, ValueError, IndexError) as error:
        raise ValueError('incomplete PCD header') from error
    if not names or len(set(names)) != len(names) or not len(names) == len(sizes) == len(types) == len(counts):
        raise ValueError('PCD field declarations do not match')
    if point_count < 0 or any(n <= 0 for n in counts):
        raise ValueError('invalid PCD dimensions')
    if 'WIDTH' in header and 'HEIGHT' in header and int(header['WIDTH'][0]) * int(header['HEIGHT'][0]) != point_count:
        raise ValueError('PCD POINTS differs from WIDTH * HEIGHT')
    fields = []
    for name, size, type_, count in zip(names, sizes, types, counts):
        if (type_ == 'F' and size not in (4, 8)) or (type_ in ('I', 'U') and size not in (1, 2, 4, 8)) or type_ not in ('F', 'I', 'U'):
            raise ValueError(f'unsupported PCD type: {type_}{size}')
        dtype = np.dtype('<' + {'F': 'f', 'I': 'i', 'U': 'u'}[type_] + str(size))
        fields.append((name, dtype) if count == 1 else (name, dtype, (count,)))
    dtype = np.dtype(fields)
    if mode == 'binary':
        if len(raw) != point_count * dtype.itemsize:
            raise ValueError(f'PCD byte count mismatch: expected {point_count * dtype.itemsize}, got {len(raw)}')
        return np.frombuffer(raw, dtype=dtype).copy()
    if mode == 'ascii':
        result = np.empty(point_count, dtype=dtype)
        if not point_count:
            if raw.strip():
                raise ValueError('unexpected data in empty PCD')
            return result
        values = np.loadtxt(io.BytesIO(raw), ndmin=2)
        if values.shape != (point_count, sum(counts)):
            raise ValueError(f'PCD ASCII shape mismatch: {values.shape}')
        offset = 0
        for name, count in zip(names, counts):
            result[name] = values[:, offset] if count == 1 else values[:, offset:offset + count]
            offset += count
        return result
    raise ValueError(f'unsupported PCD DATA format: {mode}')


def xyzi(path):
    points = read_pcd(path)
    if not all(name in points.dtype.names for name in ('x', 'y', 'z', 'intensity')):
        raise ValueError('expected scalar x, y, z and intensity fields')
    if any(points[name].ndim != 1 for name in ('x', 'y', 'z', 'intensity')):
        raise ValueError('XYZI fields must be scalar')
    return np.column_stack([points[name] for name in ('x', 'y', 'z', 'intensity')])
