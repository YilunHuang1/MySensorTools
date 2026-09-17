#!/usr/bin/env bash
# Install into this tool only; no changes to production services or global packages.
set -euo pipefail
tool_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
if [[ ! -f "$tool_dir/pyproject.toml" || ! -f "$tool_dir/sensor_tools/__init__.py" ]]; then
  echo 'Incomplete smoke bundle. Build it from the full repository with uwb/smoke_test/build_bundle.py, then extract it here.' >&2
  exit 1
fi
# The copied shared sources are already importable. Avoid editable/wheel builds on
# older robot setuptools, which can silently produce UNKNOWN without dependencies.
python3 -m pip install --upgrade --target "$tool_dir/.deps" -r "$tool_dir/requirements.txt"
PYTHONPATH="$tool_dir:$tool_dir/.deps${PYTHONPATH:+:$PYTHONPATH}" python3 -c 'import sensor_tools.aorta, sensor_tools.uwb, yaml, serial, bleak'
python3 "$tool_dir/uwb_smoke_test.py" --help >/dev/null
echo "Installed private dependencies in $tool_dir/.deps. Run python3 uwb_smoke_test.py --mode online."
