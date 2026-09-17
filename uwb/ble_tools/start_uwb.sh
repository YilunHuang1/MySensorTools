#!/usr/bin/env bash
# Own only the process started here. Never kill other Python jobs or restart Bluetooth.
set -euo pipefail
script_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
exec "${PYTHON:-python3}" "$script_dir/run_uwb_ble.py" "$@"
