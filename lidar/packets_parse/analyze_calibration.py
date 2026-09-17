#!/usr/bin/env python3
"""Summarize angular calibration tables; offsets alone do not measure accuracy."""
import argparse
from pathlib import Path
import numpy as np


def load_calibration(path):
    angles = np.loadtxt(path, delimiter=',')
    if angles.shape != (16, 2) or not np.isfinite(angles).all():
        raise ValueError('WLR-722Z calibration requires 16 finite vertical/horizontal pairs')
    return angles[:, 0], angles[:, 1]


def analyze_calibration(name, path):
    vertical, horizontal = load_calibration(path)
    if len(vertical) != 16 or not np.isfinite(vertical).all() or not np.isfinite(horizontal).all():
        raise ValueError('WLR-722Z calibration requires 16 finite channel angles')
    print(f'{name}: {path}')
    print('channel,vertical_deg,horizontal_offset_deg')
    for index,(v,h) in enumerate(zip(vertical,horizontal)):
        print(f'{index},{v:.6f},{h:.6f}')
    print(f'Vertical range: {vertical.min():.6f} .. {vertical.max():.6f} deg')
    print(f'Horizontal offset range: {horizontal.min():.6f} .. {horizontal.max():.6f} deg')
    print('Offsets are calibration coefficients, not a hardware model or accuracy grade.')
    return vertical, horizontal


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('tables',nargs='*',type=Path)
    args=parser.parse_args()
    paths=args.tables or [Path(__file__).resolve().parent/'config/calibration/Vanjee_722z_VA.csv']
    try:
        for path in paths: analyze_calibration(path.stem,path)
    except (OSError,ValueError) as error:
        parser.exit(1,f'error: {error}\n')


if __name__=='__main__':
    main()
