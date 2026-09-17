"""Shared UWB MCAP-to-CSV contract for historical and current recordings."""
import argparse
from pathlib import Path

from .mcap import iter_records, uwb_fields


def detect_version_from_path(path):
    name = str(path).lower()
    if 'close_62' in name or '062' in name:
        return '062'
    if '007' in name:
        return '007'
    return 'unknown'


def normalize_angle_for_version(angle_deg, version='unknown'):
    # Both signed and unsigned degree conventions share the same circular domain.
    return float(angle_deg) % 360.0


def iter_uwb_rows(path, topic='/uwb/data'):
    for count, record in enumerate(iter_records(path, [topic]), 1):
        result = uwb_fields(record)
        result.update(message_count=count, channel_topic=record.topic)
        yield result


def mcap_to_dataframe(mcap_file, topic_name='/uwb/data'):
    import numpy as np
    import pandas as pd
    rows = []
    version = detect_version_from_path(mcap_file)
    for row in iter_uwb_rows(mcap_file, topic_name):
        row['angle'] = normalize_angle_for_version(row['angle'], version)
        row['angle_filtered'] = normalize_angle_for_version(row['angle_filtered'], version)
        for prefix, angle, distance in [('raw', 'angle', 'distance'),
                                        ('filtered', 'angle_filtered', 'distance_filtered')]:
            radians = np.radians(row[angle])
            row[f'{prefix}_x_m'] = row[distance] * np.cos(radians)
            row[f'{prefix}_y_m'] = row[distance] * np.sin(radians)
        rows.append(row)
    return pd.DataFrame(rows)


def main():
    parser = argparse.ArgumentParser(description='Convert ROS CDR or Aorta UWB MCAP to CSV')
    parser.add_argument('mcap_file')
    parser.add_argument('-o', '--output')
    parser.add_argument('-t', '--topic', default='/uwb/data', help='logical topic or exact recorded channel')
    args = parser.parse_args()
    try:
        frame = mcap_to_dataframe(Path(args.mcap_file), args.topic)
        if frame.empty:
            raise ValueError('no matching UWB messages')
        output = Path(args.output) if args.output else Path(args.mcap_file).with_suffix('.csv')
        output.parent.mkdir(parents=True, exist_ok=True)
        frame.to_csv(output, index=False)
        print(f'{len(frame)} messages -> {output}')
    except (OSError, ValueError) as error:
        parser.exit(1, f'error: {error}\n')
    return 0
