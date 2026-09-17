import importlib.util
from pathlib import Path
import subprocess
import sys
import tarfile

import pytest

ROOT = Path(__file__).resolve().parents[1]


def test_bundle_runs_outside_checkout_without_installed_shared_package(tmp_path):
    spec = importlib.util.spec_from_file_location('smoke_bundle', ROOT / 'uwb/smoke_test/build_bundle.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    archive = module.build(tmp_path / 'smoke.tar.gz')
    deployed = tmp_path / 'deployed'
    with tarfile.open(archive) as bundle:
        assert all(not name.startswith(('/', '../')) for name in bundle.getnames())
        bundle.extractall(deployed, filter='data')
    assert (deployed / 'pyproject.toml').is_file()
    assert (deployed / 'install.sh').is_file()
    assert 'mcap' in (deployed / 'requirements.txt').read_text()
    (deployed / '.deps').mkdir()
    (deployed / '.deps/bundle_dependency_probe.py').write_text('value = 42\n')
    # -I -S excludes the editable root install and all site/PYTHONPATH dependencies.
    program = ('import runpy,sys; from pathlib import Path; '
               'runpy.run_path(sys.argv[1]); import sensor_tools,bundle_dependency_probe; '
               'assert Path(sensor_tools.__file__).parent == Path(sys.argv[1]).parent / "sensor_tools"; '
               'assert bundle_dependency_probe.value == 42')
    subprocess.run([sys.executable, '-I', '-S', '-c', program,
                    str(deployed / 'uwb_smoke_test.py')], cwd=tmp_path, check=True)
    with pytest.raises(FileExistsError):
        module.build(archive)


def test_partial_directory_reports_actionable_error(tmp_path):
    for name in ['uwb_smoke_test.py', 'report.py']:
        (tmp_path / name).write_bytes((ROOT / 'uwb/smoke_test' / name).read_bytes())
    result = subprocess.run([sys.executable, '-S', str(tmp_path / 'uwb_smoke_test.py'),
                             '--mode', 'online'], cwd=tmp_path, env={}, capture_output=True, text=True)
    assert result.returncode == 2
    assert 'complete smoke bundle' in result.stderr
    assert 'Traceback' not in result.stderr
