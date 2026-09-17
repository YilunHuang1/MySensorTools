#!/usr/bin/env python3
"""Extract ROS CDR and Aorta FlatBuffers log channels from MCAP."""
from pathlib import Path
import argparse
import contextlib
import os
import tempfile

from sensor_tools.mcap import iter_records, log_entries, topic_matches

DEFAULT_TOPIC_MAPPING = {'/x5/vlog': 'x5_vlog.txt', '/s100/vlog': 's100_vlog.txt'}


def get_log_level_str(level):
    return {0: 'UNKNOWN', 10: 'DEBUG', 20: 'INFO', 30: 'WARN', 40: 'ERROR', 50: 'FATAL'}.get(level, str(level))


def extract_logs(bag_file: str, output_dir: str, topic_mapping: dict[str, str]):
    output = Path(output_dir)
    if not Path(bag_file).is_file():
        raise FileNotFoundError(bag_file)
    if len(set(topic_mapping.values())) != len(topic_mapping):
        raise ValueError('output filenames must be unique')
    for filename in topic_mapping.values():
        if Path(filename).name != filename or filename in ('', '.', '..'):
            raise ValueError('output filenames must be simple basenames')
    output.mkdir(parents=True, exist_ok=True)
    handles, temporary, counts = {}, {}, dict.fromkeys(topic_mapping, 0)
    try:
        with contextlib.ExitStack() as stack:
            for record in iter_records(bag_file, topic_mapping):
                for topic, filename in topic_mapping.items():
                    if not topic_matches(record.topic, topic):
                        continue
                    for stamp, level, name, message, _, _, _ in log_entries(record):
                        if topic not in handles:
                            fd, temp = tempfile.mkstemp(prefix='.logs-', dir=output)
                            temporary[topic] = Path(temp)
                            handles[topic] = stack.enter_context(os.fdopen(fd, 'w', encoding='utf-8'))
                        sec, nsec = divmod(stamp, 1_000_000_000)
                        handles[topic].write(f'[{sec}.{nsec:09d}] [{get_log_level_str(level)}] [{name}]: {message}\n')
                        counts[topic] += 1
        if not sum(counts.values()):
            raise ValueError('no matching log messages; inspect the MCAP channel list')
        for topic, temp in temporary.items():
            temp.replace(output / topic_mapping[topic])
        for topic, count in counts.items():
            print(f'{topic}: {count} log entries' + (' (not present)' if not count else ''))
        return counts
    finally:
        for temp in temporary.values():
            temp.unlink(missing_ok=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('mcap')
    parser.add_argument('-o', '--output-dir', default='logs')
    parser.add_argument('--topic', action='append', default=[], metavar='TOPIC=FILE')
    args = parser.parse_args()
    mapping = DEFAULT_TOPIC_MAPPING.copy()
    if args.topic:
        mapping = {}
        for item in args.topic:
            topic, sep, filename = item.partition('=')
            if not sep or not topic or not filename:
                parser.error(f'invalid --topic mapping: {item}')
            mapping[topic] = filename
    try:
        extract_logs(args.mcap, args.output_dir, mapping)
    except (OSError, ValueError) as error:
        parser.exit(1, f'error: {error}\n')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
