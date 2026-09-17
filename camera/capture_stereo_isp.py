#!/usr/bin/env python3
"""Capture stereo streams and deployed configuration without changing camera state."""
import argparse
from collections import Counter
from datetime import datetime
import hashlib
import json
from pathlib import Path
import re
import shutil
import socket
import subprocess

from sensor_tools import aorta
from sensor_tools.mcap import iter_records


def selected_topics(mode):
    topics = ['image_left_raw/h265', 'image_right_raw/h265']
    if mode in ('isp', 'full'):
        topics += ['image_left_raw/nv12_quarter', 'image_right_raw/nv12_quarter',
                   'stereo/left/isp_status', 'stereo/right/isp_status',
                   'stereo_left/camera_info', 'stereo_right/camera_info']
    if mode == 'full':
        topics += [f'image_{side}_raw/{encoding}{scale}' for side in ('left', 'right')
                   for encoding, scale in [('h265', '_half'), ('h265', '_quarter'),
                                           ('nv12', ''), ('nv12', '_half')]]
        topics += ['image_left_raw/h265_undistort']
    return topics


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('-m', '--mode', choices=['review', 'isp', 'full'], default='isp')
    parser.add_argument('-o', '--output-root', type=Path, default=Path('/tmp/stereo_capture'))
    parser.add_argument('-l', '--label', default='manual')
    parser.add_argument('-d', '--duration', type=float, default=30, help='bounded recording in seconds (default 30)')
    parser.add_argument('--config-dir', type=Path, default=Path('/app/stereo/config'))
    args = parser.parse_args()
    if args.duration <= 0:
        parser.error('--duration must be positive')
    label = re.sub(r'[^a-zA-Z0-9_.-]', '_', args.label)
    output = args.output_root / f'{datetime.now():%Y%m%d_%H%M%S_%f}_{label}_{args.mode}'
    metadata = output / 'metadata'
    metadata.mkdir(parents=True)
    manifest = {'mode': args.mode, 'duration_requested': args.duration, 'host': socket.gethostname(),
                'started_at': datetime.now().astimezone().isoformat(), 'topics': selected_topics(args.mode),
                'missing_config_files': []}
    status = 1
    try:
        for name in ['sc230ai_tuning_sensing.json', 'node_config.json', 'nodes/stereo_camera.json', 'nodes/stereo_aorta.json']:
            source = args.config_dir / name
            if source.is_file():
                dest = metadata / 'config' / name
                dest.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(source, dest)
            else:
                manifest['missing_config_files'].append(str(source))
        manifest['registered_topics_before'] = aorta.topic_list()
        log = aorta.capture(output / 'stereo.mcap', manifest['topics'], args.duration)
        (metadata / 'record.log').write_text(log)
        counts = Counter()
        schemas = {}
        # Reading payloads as well as the index distinguishes usable messages from registration.
        for record in iter_records(output / 'stereo.mcap', manifest['topics']):
            counts[record.topic] += 1
            schemas[record.topic] = record.schema_name
        manifest['message_counts'] = dict(counts)
        manifest['schemas'] = schemas
        manifest['missing_topics'] = [topic for topic in manifest['topics'] if not any(
            channel.strip('/') == topic or channel.endswith('/pub/' + topic) for channel in counts)]
        status = 2 if manifest['missing_topics'] else 0
    except (OSError, ValueError, RuntimeError, subprocess.TimeoutExpired) as error:
        manifest['error'] = str(error)
        print(f'error: {error}')
    finally:
        manifest['finished_at'] = datetime.now().astimezone().isoformat()
        manifest['status'] = {0: 'PASS', 1: 'FAIL', 2: 'INCOMPLETE'}[status]
        (metadata / 'manifest.json').write_text(json.dumps(manifest, ensure_ascii=False, indent=2))
        checksum = metadata / 'SHA256SUMS.txt'
        with checksum.open('w') as stream:
            for path in sorted(output.rglob('*')):
                if path.is_file() and path != checksum:
                    digest = hashlib.sha256()
                    with path.open('rb') as source:
                        for chunk in iter(lambda: source.read(1024 * 1024), b''):
                            digest.update(chunk)
                    stream.write(f'{digest.hexdigest()}  {path.relative_to(output)}\n')
        print(f'Capture bundle: {output} ({manifest["status"]})')
        if manifest.get('missing_topics'):
            print('No messages: ' + ', '.join(manifest['missing_topics']))
    return status


if __name__ == '__main__':
    raise SystemExit(main())
