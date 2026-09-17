#!/usr/bin/env bash
# Keep the existing entry point; the reader verifies actual Aorta MCAP messages.
set -euo pipefail
script_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
exec "${PYTHON:-python3}" "$script_dir/capture_stereo_isp.py" "$@"
