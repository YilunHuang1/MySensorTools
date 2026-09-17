#!/usr/bin/env python3
"""Build a self-contained source bundle from the full MySensorTools checkout."""
import argparse
from pathlib import Path
import tarfile


def build(output):
    source = Path(__file__).resolve().parent
    root = source.parents[1]
    if not (root / 'sensor_tools/__init__.py').is_file():
        raise ValueError('run build_bundle.py from the full MySensorTools checkout')
    output = Path(output)
    output.parent.mkdir(parents=True, exist_ok=True)
    # Explicit source-only selection prevents private captures/reports entering the bundle.
    files = [(p, p.name) for p in sorted(source.glob('*.py')) if p.name != 'build_bundle.py']
    files += [(source / name, name) for name in ['README.md', 'install.sh', 'requirements.txt']]
    files += [(root / 'pyproject.toml', 'pyproject.toml')]
    files += [(p, 'sensor_tools/' + p.name) for p in sorted((root / 'sensor_tools').glob('*.py'))]
    with output.open('xb') as stream, tarfile.open(fileobj=stream, mode='w:gz') as archive:
        for path, name in files:
            archive.add(path, arcname=name, recursive=False)
    return output


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    try:
        print(build(args.output))
    except (OSError, ValueError) as error:
        parser.exit(1, f'error: {error}\n')
