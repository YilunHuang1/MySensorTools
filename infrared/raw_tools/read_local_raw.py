#!/usr/bin/env python3
"""Convert a RAW image using explicit dimensions and pixel format; never truncate."""
import argparse
from pathlib import Path
from sensor_tools.images import image_array, save_image


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('raw_file')
    parser.add_argument('--width', type=int, required=True)
    parser.add_argument('--height', type=int, required=True)
    parser.add_argument('--encoding', choices=['mono8', 'yuyv', 'uyvy', 'nv12', 'rgb8', 'bgr8'], default='mono8')
    parser.add_argument('--step', type=int, help='Bytes per row, including padding')
    parser.add_argument('--output-dir', default='output')
    args = parser.parse_args()
    try:
        image = image_array(Path(args.raw_file).read_bytes(), args.width, args.height, args.encoding, args.step)
        output = Path(args.output_dir) / (Path(args.raw_file).stem + '.png')
        save_image(output, image)
        print(f'{args.encoding} {args.width}x{args.height} -> {output}')
    except (OSError, ValueError) as error:
        parser.exit(1, f'error: {error}\n')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
