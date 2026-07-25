#!/usr/bin/env bash
# Capture stereo ISP evidence without changing camera, ISP, or robot state.
set -Eeuo pipefail
umask 022

readonly DEFAULT_OUTPUT_ROOT="/tmp/stereo_capture"
readonly ENV_SCRIPT="/app/script/env.sh"
readonly STEREO_CONFIG_DIR="/app/stereo/config"

output_root="${DEFAULT_OUTPUT_ROOT}"
label="manual"
duration_sec=0
mode="isp"

usage() {
  cat <<'EOF'
Usage: stereo_capture_1107.sh [options]

Modes:
  review  Record left/right full-resolution H.265 for subjective review.
  isp     Record left/right full H.265, quarter NV12, ISP status and CameraInfo.
           This is the default and is recommended for ISP tuning.
  full    Record all configured H.265/NV12 scales plus ISP status and CameraInfo.

Options:
  -m, --mode MODE         review | isp | full (default: isp)
  -o, --output-root DIR   Parent directory (default: /tmp/stereo_capture)
  -l, --label NAME        Scene label in the output directory (default: manual)
  -d, --duration SEC      Stop automatically after SEC seconds; 0 means Ctrl-C
  -h, --help              Show this help

Examples:
  /root/stereo_capture_1107.sh -m review -l p0-01_office -d 30
  /root/stereo_capture_1107.sh -m isp -l p0-03_mixed_light -d 45
  /root/stereo_capture_1107.sh -m full -l pipeline_debug
EOF
}

while ((${#} > 0)); do
  case "$1" in
    -m|--mode) mode="$2"; shift 2 ;;
    -o|--output-root) output_root="$2"; shift 2 ;;
    -l|--label) label="$2"; shift 2 ;;
    -d|--duration) duration_sec="$2"; shift 2 ;;
    -h|--help) usage; exit 0 ;;
    *) echo "Unknown option: $1" >&2; usage >&2; exit 2 ;;
  esac
done

case "$mode" in review|isp|full) ;; *) echo "--mode must be review, isp, or full" >&2; exit 2 ;; esac
[[ "$duration_sec" =~ ^[0-9]+$ ]] || { echo "--duration must be a non-negative integer" >&2; exit 2; }
[[ -r "$ENV_SCRIPT" ]] || { echo "Missing ROS environment: $ENV_SCRIPT" >&2; exit 1; }
source "$ENV_SCRIPT"
command -v ros2 >/dev/null || { echo "ros2 unavailable" >&2; exit 1; }

case "$mode" in
  review) topics=(/image_left_raw/h265 /image_right_raw/h265) ;;
  isp) topics=(
    /image_left_raw/h265 /image_right_raw/h265
    /image_left_raw/nv12_quarter /image_right_raw/nv12_quarter
    /stereo/left/isp_status /stereo/right/isp_status
    /stereo_left/camera_info /stereo_right/camera_info
  ) ;;
  full) topics=(
    /image_left_raw/h265 /image_right_raw/h265
    /image_left_raw/h265_half /image_right_raw/h265_half
    /image_left_raw/h265_quarter /image_right_raw/h265_quarter
    /image_left_raw/nv12_half
    /image_left_raw/nv12_quarter /image_right_raw/nv12_quarter
    /stereo/left/isp_status /stereo/right/isp_status
    /stereo_left/camera_info /stereo_right/camera_info
  ) ;;
esac

timestamp="$(date +%Y%m%d_%H%M%S)"
safe_label="$(printf '%s' "$label" | tr -cs '[:alnum:]_.-' '_')"
capture_dir="${output_root%/}/${timestamp}_${safe_label}_${mode}"
metadata_dir="${capture_dir}/metadata"
bag_dir="${capture_dir}/stereo.mcap"
mkdir -p "$metadata_dir"
bag_pid=""

capture_runtime_metadata() {
  local phase="$1"
  {
    echo "capture_phase=$phase"
    echo "capture_mode=$mode"
    date -Is
    hostname
    uname -a
    echo "--- stereo process ---"
    ps -ef | grep -E '[s]tereo_exec|[c]amera_encode' || true
    echo "--- ROS graph ---"
    ros2 topic list || true
    ros2 node list || true
  } >"${metadata_dir}/runtime_${phase}.txt" 2>&1
  if [[ "$mode" != "review" ]]; then
    local topic side
    for topic in /stereo/left/isp_status /stereo/right/isp_status; do
      side="${topic#/stereo/}"; side="${side%/isp_status}"
      timeout 8 ros2 topic echo --once "$topic" >"${metadata_dir}/isp_status_${side}_${phase}.yaml" 2>&1 || true
    done
  fi
}

copy_static_evidence() {
  {
    echo "--- ISP JSON ---"
    ls -l "$STEREO_CONFIG_DIR/sc230ai_tuning_sensing.json" || true
    md5sum "$STEREO_CONFIG_DIR/sc230ai_tuning_sensing.json" || true
    sha256sum "$STEREO_CONFIG_DIR/sc230ai_tuning_sensing.json" || true
    echo "--- deployed stereo executable ---"
    md5sum /app/stereo/stereo_exec || true
    sha256sum /app/stereo/stereo_exec || true
  } >"${metadata_dir}/config_manifest.txt" 2>&1
  for config in "$STEREO_CONFIG_DIR/sc230ai_tuning_sensing.json" "$STEREO_CONFIG_DIR/node_config.json" "$STEREO_CONFIG_DIR/nodes/stereo_camera.json"; do
    [[ -r "$config" ]] && cp --preserve=mode,timestamps "$config" "$metadata_dir/"
  done
  if command -v python3 >/dev/null; then
    python3 - "$STEREO_CONFIG_DIR/sc230ai_tuning_sensing.json" >"${metadata_dir}/isp_summary.json" 2>&1 <<'PY' || true
import json, sys
with open(sys.argv[1], encoding="utf-8") as file:
    tuning = json.load(file)
header = tuning.get("header", {})
awb = tuning.get("sensor", {}).get("AWB", {})
global_awb = (awb.get("globals") or [{}])[0]
modules = tuning.get("tuning", {})
print(json.dumps({
    "header": {key: header.get(key) for key in ("creation_date", "creator", "sensor_name", "sample_name", "generator_version", "resolution")},
    "awb_global": {key: global_awb.get(key) for key in ("fRgProjIndoorMin", "fRgProjMax", "fRgProjMaxSky", "fRgProjOutdoorMin", "IIR")},
    "awb_illumination": [{"name": item.get("name"), "doorType": item.get("doorType"), "manualWB": item.get("manualWB"), "manualccMatrix": item.get("manualccMatrix")} for item in awb.get("illumination", [])],
    "module_presence": {"WDR_5_2_1": "WDR_5_2_1" in modules, "HDR_3_2DOL": "HDR_3_2DOL" in modules},
}, ensure_ascii=False, indent=2))
PY
  fi
}

write_topic_metadata() {
  local topic filename
  for topic in "${topics[@]}"; do
    filename="$(printf '%s' "$topic" | tr '/' '_')"
    ros2 topic info -v "$topic" >"${metadata_dir}/topic${filename}.txt" 2>&1 || true
  done
}

finish() {
  local status=$?
  trap - EXIT INT TERM
  if [[ -n "$bag_pid" ]] && kill -0 "$bag_pid" 2>/dev/null; then
    kill -INT "$bag_pid" 2>/dev/null || true
    wait "$bag_pid" || true
  fi
  capture_runtime_metadata end
  copy_static_evidence
  [[ -d "$bag_dir" ]] && ros2 bag info "$bag_dir" >"${metadata_dir}/rosbag_info.txt" 2>&1 || true
  (cd "$capture_dir" && find . -type f -print0 | sort -z | xargs -0 sha256sum) >"${metadata_dir}/SHA256SUMS.txt" 2>&1 || true
  echo "Capture bundle: $capture_dir"
  exit "$status"
}
trap finish EXIT INT TERM

capture_runtime_metadata start
copy_static_evidence
write_topic_metadata
echo "Mode: $mode"
printf '  %s\n' "${topics[@]}"
echo "Operate the dog, then press Ctrl-C to stop. Output: $capture_dir"

if ((duration_sec > 0)); then
  timeout --signal=INT "${duration_sec}s" ros2 bag record --storage mcap --output "$bag_dir" "${topics[@]}" >"${metadata_dir}/rosbag_record.log" 2>&1 &
else
  ros2 bag record --storage mcap --output "$bag_dir" "${topics[@]}" >"${metadata_dir}/rosbag_record.log" 2>&1 &
fi
bag_pid=$!
wait "$bag_pid"
