#!/usr/bin/env python3
"""Stage the BLE bench tool in a new isolated robot directory. Does not start it."""
import argparse
from datetime import datetime
from pathlib import Path
import re
import shlex
import subprocess
import tarfile
import tempfile


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--host', required=True, help='SSH alias or user@host')
    parser.add_argument('--remote-dir', default=f'/tmp/uwb-bench-{datetime.now():%Y%m%d-%H%M%S}')
    args = parser.parse_args()
    if not re.fullmatch(r'[A-Za-z0-9_@.:-]+', args.host) or args.host.startswith('-'):
        parser.error('invalid SSH host')
    if not re.fullmatch(r'/[A-Za-z0-9_./-]+', args.remote_dir) or '..' in Path(args.remote_dir).parts:
        parser.error('remote directory must be an absolute path without shell metacharacters')
    source = Path(__file__).resolve().parent
    with tempfile.TemporaryDirectory(prefix='uwb-deploy-') as temp:
        archive = Path(temp) / 'tool.tar.gz'
        with tarfile.open(archive, 'w:gz') as tar:
            for name in ['run_uwb_ble.py', 'SerialHandlerStandalone.py', 'CmdBuilder.py', 'PacketParser.py', 'crc16_utils.py', 'start_uwb.sh']:
                tar.add(source / name, arcname=name)
            for path in sorted((source / 'sensor_tools').glob('*.py')):
                tar.add(path, arcname='sensor_tools/' + path.name)
        remote = shlex.quote(args.remote_dir)
        # mkdir without -p is intentional: never overwrite an earlier installation.
        subprocess.run(['ssh', args.host, f'mkdir -- {remote}'], check=True)
        subprocess.run(['scp', str(archive), f'{args.host}:{args.remote_dir}/tool.tar.gz'], check=True)
        script = (f'cd {remote} && tar -xzf tool.tar.gz && '
                  'python3 -m pip install --target deps pyserial==3.5 && '
                  'PYTHONPATH=.:deps python3 -c "import serial, dbus; from gi.repository import GLib"')
        subprocess.run(['ssh', args.host, script], check=True)
    print('Staged; production services and Bluetooth were not changed.')
    print(f'On {args.host}: cd {shlex.quote(args.remote_dir)}')
    print('PYTHONPATH=.:deps bash start_uwb.sh --help')
    print('After isolating the bench serial device: PYTHONPATH=.:deps bash start_uwb.sh --port /dev/ttyUSB0 --allow-device-control')


if __name__ == '__main__':
    try:
        main()
    except (OSError, subprocess.CalledProcessError) as error:
        raise SystemExit(f'deployment failed: {error}')
