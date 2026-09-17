#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
PYTHON="${PYTHON:-python3}"
"$PYTHON" -c 'import sys; assert sys.version_info >= (3, 10), "Python 3.10+ required"'
"$PYTHON" -m pip install -r "$ROOT/requirements.txt"
"$PYTHON" "$ROOT/uwb_analysis_pipeline.py" --self-test
printf 'Ready: %s\n' "$PYTHON $ROOT/uwb_analysis_pipeline.py --help"
