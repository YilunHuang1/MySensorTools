"""Bounded Aorta CLI access using the same environment as deployed services."""
from __future__ import annotations

import json
import math
import os
from pathlib import Path
import shutil
import signal
import subprocess
import tempfile


def executable(name):
    override = os.environ.get('AORTA_CLI' if name == 'aorta' else 'AORTA_RECORDER')
    path = override or shutil.which(name)
    if not path and Path('/app/aorta/bin', name).is_file():
        path = str(Path('/app/aorta/bin', name))
    if not path:
        raise FileNotFoundError(f'{name} not found; set AORTA_CLI/AORTA_RECORDER or run on the robot')
    return path


def command(name, arguments):
    argv = [executable(name), *map(str, arguments)]
    environment_script = Path(os.environ.get('AORTA_ENV_SCRIPT', '/app/script/env.sh'))
    if environment_script.is_file():
        # Positional arguments avoid interpolating topics/paths/requests into shell code.
        return ['bash', '-c', 'set -e; source "$1"; shift; exec "$@"', 'sensor-tools', str(environment_script), *argv]
    return argv


def run(arguments, timeout=10, name='aorta'):
    result = subprocess.run(command(name, arguments), capture_output=True, text=True, timeout=timeout)
    if result.returncode:
        raise RuntimeError(f'{name} exited {result.returncode}: {result.stderr.strip() or result.stdout.strip()}')
    return result.stdout


def objects(text):
    """Read CLI JSON/FlatBuffers-text objects without interpreting banners as data."""
    import yaml
    start, depth, quoted, escaped = None, 0, False, False
    for index, char in enumerate(text):
        if quoted:
            if escaped:
                escaped = False
            elif char == '\\':
                escaped = True
            elif char == '"':
                quoted = False
            continue
        if char == '"':
            quoted = True
        elif char == '{':
            if depth == 0:
                start = index
            depth += 1
        elif char == '}':
            depth -= 1
            if depth < 0:
                raise ValueError('unbalanced CLI object')
            if depth == 0:
                value = yaml.safe_load(text[start:index + 1])
                if not isinstance(value, dict):
                    raise ValueError('expected CLI message object')
                yield value
    if depth or quoted:
        raise ValueError('incomplete CLI message')


def echo(topic, count=1, timeout=10):
    if count < 1:
        raise ValueError('count must be positive')
    messages = list(objects(run(['topic', 'echo', topic, '--count', count], timeout)))
    if len(messages) != count:
        raise ValueError(f'{topic}: expected {count} messages, received {len(messages)}')
    return messages


def topic_list():
    result = json.loads(run(['--format', 'json', 'topic', 'list']))
    if not isinstance(result, list):
        raise ValueError('unexpected topic-list response')
    return [item['topic'] for item in result]


def call(service, request, timeout=10):
    response = list(objects(run(['service', 'call', service, json.dumps(request), '--timeout', str(max(1, timeout - 2))], timeout)))
    if not response:
        raise ValueError(f'{service}: no response object')
    return response[-1]


def capture(output, topics, duration=5, *, group=None):
    """Record a bounded passive sample, excluding unrelated contexts and telemetry."""
    output = Path(output)
    if not math.isfinite(duration) or duration <= 0:
        raise ValueError('capture duration must be finite and positive')
    # aorta-record accepts integer seconds; round up so a requested window is not shortened.
    duration = math.ceil(duration)
    if output.exists():
        raise FileExistsError(output)
    if not topics:
        raise ValueError('capture needs explicit topics')
    suffixes = []
    for topic in topics:
        parts = topic.strip('/').split('/')
        if len(parts) >= 4 and parts[0] == 'aorta':
            if parts[2] != 'pub':
                raise ValueError('capture accepts pub topics only')
            if group is not None and group != parts[1]:
                raise ValueError('one capture cannot mix Aorta groups')
            group = parts[1]
            suffixes.append('/'.join(parts[3:]))
        else:
            suffixes.append(topic.lstrip('/'))
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='.aorta-capture-', dir=output.parent) as directory:
        temporary = Path(directory) / 'sample.mcap'
        args = ['--output', str(temporary), '--duration', str(duration), '--no-ctx-snapshot',
                '--blacklist-full', 'aorta/*/ctx/**', '--blacklist-full', 'aorta/*/sys/**']
        if group:
            args += ['--group', group]
        for topic in suffixes:
            args += ['--include', topic]
        process = subprocess.Popen(command('aorta-record', args), stdout=subprocess.PIPE,
                                   stderr=subprocess.PIPE, text=True, start_new_session=True)
        try:
            stdout, stderr = process.communicate(timeout=duration + 30)
        except BaseException:
            # Stop only our recorder and give it time to finalize; never touch production services.
            if process.poll() is None:
                os.killpg(process.pid, signal.SIGINT)
                try:
                    process.communicate(timeout=5)
                except subprocess.TimeoutExpired:
                    os.killpg(process.pid, signal.SIGKILL)
                    process.communicate()
            raise
        if process.returncode:
            raise RuntimeError(f'recorder exited {process.returncode}: {stderr.strip()}')
        if not temporary.is_file() or temporary.stat().st_size == 0:
            raise ValueError('recorder produced no file')
        temporary.replace(output)
        return stdout + stderr
