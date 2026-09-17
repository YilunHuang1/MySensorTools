#!/usr/bin/env python3
"""Export grayscale frames from ROS Image or Aorta RawImage MCAP channels.

Current infrared frames are mono8 and pass through unchanged. Legacy YUYV
frames are converted using their encoding and step fields. No robot state changes.
"""
import argparse
import csv
from pathlib import Path
from sensor_tools.images import raw_image, save_image
from sensor_tools.mcap import iter_records, source_time_ns


def convert(mcap, output_dir, topic='/infrared_camera/image_raw', max_frames=100):
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    if max_frames < 1:
        raise ValueError('max_frames must be positive')
    rows = []
    for record in iter_records(mcap, [topic]):
        image = raw_image(record.data, grayscale=True)
        stamp = source_time_ns(record.data, record.publish_time_ns)
        name = f'frame_{len(rows):06d}_{stamp}.png'
        save_image(output / name, image)
        rows.append(dict(file=name, source_time_ns=stamp, log_time_ns=record.log_time_ns,
                         topic=record.topic, encoding=record.data['encoding'],
                         width=image.shape[1], height=image.shape[0]))
        if len(rows) >= max_frames:
            break
    if not rows:
        raise ValueError('no infrared images found')
    with (output / 'frames.csv').open('w', newline='', encoding='utf-8') as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    return len(rows)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('mcap')
    parser.add_argument('--topic', default='/infrared_camera/image_raw')
    parser.add_argument('--output-dir', default='output/infrared')
    parser.add_argument('--max-frames', type=int, default=100)
    args = parser.parse_args()
    try:
        print(f'Exported {convert(args.mcap, args.output_dir, args.topic, args.max_frames)} frames')
    except (OSError, ValueError) as error:
        parser.exit(1, f'error: {error}\n')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
