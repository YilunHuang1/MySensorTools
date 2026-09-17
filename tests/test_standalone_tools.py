"""Exercise copied tools with no root editable install or sibling checkout available."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

import pytest

ROOT = Path(__file__).resolve().parents[1]
TOOLS = json.loads((ROOT / 'tests/standalone_tools.json').read_text())
# Add dependency directories manually with -S: do not process editable-install .pth files.
DEPENDENCIES = [p for p in sys.path if p and ('site-packages' in p or 'dist-packages' in p)]
FILES = subprocess.check_output(['git', 'ls-files', '-c', '-o', '--exclude-standard', '-z'], cwd=ROOT).decode().split('\0')


def copy_tool(folder, destination):
    for relative in FILES:
        if not relative.startswith(folder + '/') or relative.endswith('/Untitled'):
            continue
        source = ROOT / relative
        if not source.is_file():
            continue
        target = destination / source.relative_to(ROOT / folder)
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, target)


def run_tool(folder, entry, *args, cwd=None):
    script = folder / entry
    program = ('import json,runpy,sys; from pathlib import Path; '
               'sys.path.extend(json.loads(sys.argv[1])); '
               'sys.path.insert(0,str(Path(sys.argv[2]).parent)); '
               'sys.argv=sys.argv[2:]; runpy.run_path(sys.argv[0],run_name="__main__")')
    env = {k: v for k, v in os.environ.items() if k != 'PYTHONPATH'}
    env.update(MPLBACKEND='Agg', MPLCONFIGDIR=str(folder / '.mpl'), XDG_CACHE_HOME=str(folder / '.cache'))
    return subprocess.run([sys.executable, '-S', '-c', program, json.dumps(DEPENDENCIES),
                           str(script), *map(str, args)], cwd=cwd or folder, env=env,
                          capture_output=True, text=True, timeout=30)


@pytest.mark.parametrize('tool', TOOLS, ids=[t['folder'] for t in TOOLS])
def test_independent_folder_imports_and_entrypoints(tmp_path, tool):
    folder = tmp_path / 'tool'
    copy_tool(tool['folder'], folder)
    requirements = (folder / 'requirements.txt').read_text()
    assert '-e ' not in requirements and 'my-sensor-tools' not in requirements
    modules = tool['modules']
    if modules:
        assert {p.stem for p in (folder / 'sensor_tools').glob('*.py')} == set(modules) | {'__init__'}
        for name in ['__init__', *modules]:
            assert (folder / 'sensor_tools' / f'{name}.py').read_bytes() == (ROOT / 'sensor_tools' / f'{name}.py').read_bytes()
    for entry in tool['entries']:
        result = run_tool(folder, entry, '--help', cwd=tmp_path)
        assert result.returncode == 0, (tool['folder'], entry, result.stdout, result.stderr)
    if tool['folder'] == 'camera/isp_json':
        (tmp_path / 'one.json').write_text('{"gain":1}')
        (tmp_path / 'two.json').write_text('{"gain":2}')
        result = run_tool(folder, 'compare_json.py', tmp_path / 'one.json', tmp_path / 'two.json')
        assert result.returncode == 0 and 'MODIFIED: gain' in result.stdout
    if tool['folder'] == 'lidar/packets_parse/foxglove':
        assert (folder / 'Vanjee_722z_VA.csv').read_bytes() == (ROOT / 'lidar/packets_parse/config/calibration/Vanjee_722z_VA.csv').read_bytes()


def test_copied_common_does_not_write_beside_install_directory(tmp_path):
    folder = tmp_path / 'installed' / 'common'
    copy_tool('common', folder)
    work = tmp_path / 'work'; work.mkdir()
    result = run_tool(folder, 'create_debug_case.py', '--case-id', 'example', cwd=work)
    assert result.returncode == 0, result.stderr
    assert (work / 'debug_cases/example/issue.yaml').is_file()
    assert not (folder.parent / 'debug_cases').exists()


def synthetic_mcap(path):
    import base64
    from mcap.writer import Writer
    with path.open('wb') as stream:
        writer = Writer(stream); writer.start()
        schema = writer.register_schema('fixture.Message', 'jsonschema', b'{"type":"object"}')
        topics = {
            'uwb/ranging': dict(distance=1.0, angle=10., pitch=0., distance_filtered=1.0, angle_filtered=10., pos_confidence=90),
            'infrared_camera/image_raw': dict(width=64, height=48, encoding='mono8', step=64, data=base64.b64encode(bytes([128]) * 64 * 48).decode()),
            'imu_raw': dict(frame_id='imu', angular_velocity=dict(x=0., y=0., z=0.), linear_acceleration=dict(x=0., y=0., z=1.)),
            'x5/vlog': dict(level=20, name='fixture', message='independent folder test'),
        }
        for topic, data in topics.items():
            channel = writer.register_channel('aorta/default/pub/' + topic, 'json', schema)
            for i in range(5):
                stamp = 1_000_000_000 + i * 50_000_000
                writer.add_message(channel, stamp, json.dumps(data).encode(), stamp, i)
        writer.finish()


@pytest.mark.parametrize('folder,entry,arguments,artifact', [
    ('uwb/truth_value_analysis', 'mcap_to_csv_cdr_correct.py', ['input.mcap', '-o', 'out.csv'], 'out.csv'),
    ('uwb/mcap_tools/uwb_data_b1_b2_compare', 'mcap_to_csv_cdr_correct.py', ['input.mcap', '-o', 'out.csv'], 'out.csv'),
    ('uwb/mcap_tools/vis_ansys', 'mcap_to_csv.py', ['input.mcap', '-o', 'out.csv', '--stream'], 'out.csv'),
    ('common', 'parse_mcap_log.py', ['input.mcap', '-o', 'logs'], 'logs'),
    ('imu/mcap_analysis', 'analyze_imu_mcap.py', ['analyze', 'input.mcap', '--topics', '/imu_raw'], None),
    ('infrared/raw_tools', 'IrConverter.py', ['input.mcap', '--output-dir', 'images'], 'images/frames.csv'),
    ('infrared/ir_qr_bench', 'ir_qr_bench.py', ['--mcap', 'input.mcap', '--image-save-dir', 'bench'], 'bench'),
])
def test_copied_tools_process_data(tmp_path, folder, entry, arguments, artifact):
    tool = tmp_path / 'tool'; copy_tool(folder, tool)
    synthetic_mcap(tool / 'input.mcap')
    result = run_tool(tool, entry, *arguments)
    assert result.returncode == 0, (folder, result.stdout, result.stderr)
    if artifact:
        assert (tool / artifact).exists()


@pytest.mark.parametrize('old_timeout', [False, True])
def test_online_smoke_can_pass_ranging_in_copied_directory(tmp_path, old_timeout):
    tool = tmp_path / 'tool'; copy_tool('uwb/smoke_test', tool)
    synthetic_mcap(tool / 'source.mcap')
    # Substitute only robot executables: exercise capture, decode, checks and reporting.
    cli = tool / 'fake_aorta'
    cli.write_text('#!' + sys.executable + '\nimport json,sys\n'
                   'a=sys.argv\n'
                   'if "echo" in a: r={"state":"RANGING","battery_percentage":80}\n'
                   'elif "firmware_version/uwb" in a: r={"status":"SUCCESS","versions":[{"name":"uwb_anchor","sw_version":"5.2.4"},{"name":"uwb_tag","sw_version":"0.2.20"}]}\n'
                   'else: r={"status":"SUCCESS","error_code":0,"fault_info_array":' +
                   repr([dict(fault_id=0x40060102, timestamp_ns=1, status=0)] if old_timeout else []) + '}\n'
                   'print(json.dumps(r))\n')
    recorder = tool / 'fake_recorder'
    recorder.write_text('#!' + sys.executable + '\nimport shutil,sys\nfrom pathlib import Path\n'
                        'shutil.copyfile(Path(__file__).with_name("source.mcap"),sys.argv[sys.argv.index("--output")+1])\n')
    cli.chmod(0o755); recorder.chmod(0o755)
    env = dict(os.environ, AORTA_CLI=str(cli), AORTA_RECORDER=str(recorder), AORTA_ENV_SCRIPT=str(tool / 'absent'))
    from unittest.mock import patch
    with patch.dict(os.environ, env, clear=True):
        result = run_tool(tool, 'uwb_smoke_test.py', '--mode', 'online', '--ranging-duration', '1')
    assert result.returncode == 0, (result.stdout, result.stderr)
    report = json.loads(next(tool.glob('smoke_test_report_*.json')).read_text())
    assert report['overall'] == 'PASS'
    ranging = next(r for r in report['results'] if r['name'] == '测距功能')
    assert ranging['data']['frame_count'] == 5 and ranging['data']['frame_rate'] == 20
    assert ranging['data']['min_frame_rate'] == 18
    faults = next(r for r in report['results'] if r['name'] == '系统当前故障')
    assert len(faults['data']['non_blocking_faults']) == int(old_timeout)
