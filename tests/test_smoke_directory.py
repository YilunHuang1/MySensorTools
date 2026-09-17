from pathlib import Path
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
SMOKE = ROOT / 'uwb/smoke_test'


def test_copied_directory_resolves_its_own_runtime(tmp_path):
    deployed = tmp_path / 'smoke_test'
    shutil.copytree(SMOKE, deployed, ignore=shutil.ignore_patterns('__pycache__'))
    # -I -S excludes the root editable install, PYTHONPATH and all site packages.
    program = ('import runpy,sys; from pathlib import Path; '
               'runpy.run_path(sys.argv[1]); import sensor_tools.aorta,sensor_tools.uwb_serial; '
               'assert Path(sensor_tools.aorta.__file__).parent == Path(sys.argv[1]).parent / "sensor_tools"')
    subprocess.run([sys.executable, '-I', '-S', '-c', program,
                    str(deployed / 'uwb_smoke_test.py')], cwd=tmp_path, check=True)
    assert not (deployed / 'pyproject.toml').exists()
    assert not (deployed / 'install.sh').exists()


def test_missing_dependencies_explain_normal_install_command(tmp_path):
    shutil.copytree(SMOKE, tmp_path / 'smoke', ignore=shutil.ignore_patterns('__pycache__'))
    result = subprocess.run([sys.executable, '-S', str(tmp_path / 'smoke/uwb_smoke_test.py'),
                             '--mode', 'online'], cwd=tmp_path, env={}, capture_output=True, text=True)
    assert result.returncode == 2
    assert 'python3 -m pip install -r requirements.txt' in result.stderr
    assert 'Traceback' not in result.stderr


def test_embedded_runtime_does_not_drift_from_tested_shared_readers():
    expected = {'__init__.py', 'aorta.py', 'mcap.py', 'flatbuffer.py', 'uwb.py', 'uwb_serial.py'}
    embedded = SMOKE / 'sensor_tools'
    assert {p.name for p in embedded.glob('*.py')} == expected
    for name in expected:
        assert (embedded / name).read_bytes() == (ROOT / 'sensor_tools' / name).read_bytes(), name
