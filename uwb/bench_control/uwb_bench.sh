#!/bin/bash
#
# X5-local UWB bench controller.
# Install to /app/uwb/uwb_bench.sh and run directly on X5.

set -uo pipefail

# Change this value when the bench normally uses another Tag. The start command
# argument takes precedence, so editing the file is optional.
DEFAULT_TAG_NAME="Vbot_F274C9EC1DB0"

ROS_ENV="/app/script/env.sh"
WAIT_TIMEOUT_S=45
POLL_INTERVAL_S=2

log() {
  printf '[%s] %s\n' "$1" "$2"
}

die() {
  log ERROR "$1" >&2
  return 1
}

load_ros_env() {
  if [[ ! -f "${ROS_ENV}" ]]; then
    die "ROS environment not found: ${ROS_ENV}"
    return 1
  fi
  # shellcheck disable=SC1090
  source "${ROS_ENV}"
}

call_service() {
  local description="$1"
  shift
  local output=""
  local attempt

  for attempt in 1 2 3; do
    output="$(timeout -k 2 18 "$@" 2>&1 || true)"
    if [[ "${output}" == *"success=True"* ]]; then
      log OK "${description}"
      return 0
    fi
    if (( attempt < 3 )); then
      log INFO "${description} unavailable; retrying (${attempt}/3)"
      sleep 2
    fi
  done

  printf '%s\n' "${output}" >&2
  die "${description} failed"
}

execute_s100() {
  local command="$1"
  local description="$2"
  call_service "${description}" \
    ros2 service call /execute_s100_command \
    software_msgs/srv/ExecuteCommand \
    "{command: '${command}'}"
}

stop_vln() {
  execute_s100 "systemctl stop vln.service" \
    "S100 vln.service stopped"
}

start_vln() {
  execute_s100 "systemctl start vln.service" \
    "S100 vln.service restored"
}

set_follow_context() {
  local mode="$1"
  local status="$2"
  local request_id="$3"

  call_service "Follow Context mode=${mode} status=${status}" \
    ros2 service call /function/context/set_context \
    function_msgs/srv/SetContext \
    "{keys: [FOLLOW_MODE, FOLLOW_STATUS], values: ['${mode}', '${status}'], source_node: uwb_bench, request_id: ${request_id}}"
}

pair_tag() {
  local tag_name="$1"
  call_service "Tag pairing configured: ${tag_name}" \
    ros2 service call /uwb/pair_tag \
    uwb_msgs/srv/Pair \
    "{tag_name: '${tag_name}', precode: 0}"
}

get_uwb_state() {
  local output
  output="$(timeout -k 2 12 ros2 topic echo /uwb/state --once 2>/dev/null || true)"
  printf '%s\n' "${output}" | awk '/^state:/ {print $2; exit}'
}

state_name() {
  case "$1" in
    0) printf 'IDLE' ;;
    1) printf 'CONNECTED' ;;
    2) printf 'RANGING' ;;
    *) printf 'UNKNOWN' ;;
  esac
}

wait_for_state() {
  local accepted="$1"
  local description="$2"
  local deadline=$((SECONDS + WAIT_TIMEOUT_S))
  local state=""

  while (( SECONDS < deadline )); do
    state="$(get_uwb_state)"
    if [[ ",${accepted}," == *",${state},"* ]]; then
      log OK "UWB ${description}: $(state_name "${state}")"
      return 0
    fi
    sleep "${POLL_INTERVAL_S}"
  done

  die "UWB did not reach ${description}; last state=$(state_name "${state}")"
}

restart_bluetooth_stack() {
  log INFO "Restarting X5 Bluetooth/BLE/UWB services"
  systemctl restart bluetooth.service || return 1
  systemctl restart ble.service || return 1
  systemctl restart uwb.service || return 1

  systemctl is-active --quiet bluetooth.service || return 1
  systemctl is-active --quiet ble.service || return 1
  systemctl is-active --quiet uwb.service || return 1
  log OK "X5 Bluetooth/BLE/UWB services active"
}

wait_for_connection_with_recovery() {
  if wait_for_state "1,2" "connected"; then
    return 0
  fi
  restart_bluetooth_stack || return 1
  wait_for_state "1,2" "connected after stack restart"
}

print_data_sample() {
  local sample=""
  local attempt

  for attempt in 1 2 3; do
    sample="$(timeout -k 2 15 ros2 topic echo /uwb/data --once 2>/dev/null || true)"
    if [[ "${sample}" == *"distance:"* ]]; then
      local distance angle confidence
      distance="$(printf '%s\n' "${sample}" |
        awk '/^distance_filtered:/ {print $2; exit}')"
      angle="$(printf '%s\n' "${sample}" |
        awk '/^angle_filtered:/ {print $2; exit}')"
      confidence="$(printf '%s\n' "${sample}" |
        awk '/^pos_confidence:/ {print $2; exit}')"
      log OK "Sample distance=${distance}m angle=${angle}deg confidence=${confidence}"
      return 0
    fi

    if [[ "$(get_uwb_state)" != "2" ]]; then
      die "UWB left RANGING while waiting for /uwb/data"
      return 1
    fi
    log INFO "No /uwb/data yet; retrying (${attempt}/3)"
  done

  die "RANGING active but no /uwb/data received"
}

validate_tag_name() {
  local tag_name="$1"
  if [[ ! "${tag_name}" =~ ^Vbot_[0-9A-Fa-f]{12,32}$ ]]; then
    die "Invalid Tag name: ${tag_name}"
    return 1
  fi
}

safe_rollback() {
  log INFO "Rolling back to a safe bench state"
  set_follow_context 0 0 "uwb-bench-failed" || true
  start_vln || true
}

start_ranging() {
  local tag_name="$1"
  validate_tag_name "${tag_name}" || return 1

  stop_vln || return 1
  if ! set_follow_context 0 0 "uwb-bench-prepare"; then
    start_vln || true
    return 1
  fi
  if ! pair_tag "${tag_name}"; then
    safe_rollback
    return 1
  fi
  if ! wait_for_connection_with_recovery; then
    safe_rollback
    return 1
  fi
  if ! set_follow_context 1 1 "uwb-bench-start"; then
    safe_rollback
    return 1
  fi
  if ! wait_for_state "2" "ranging"; then
    safe_rollback
    return 1
  fi
  if ! print_data_sample; then
    safe_rollback
    return 1
  fi

  log OK "UWB ranging is running; S100 vln.service remains stopped"
}

stop_ranging() {
  set_follow_context 0 0 "uwb-bench-stop" || return 1
  wait_for_state "0,1" "stopped" || return 1
  start_vln || return 1
  log OK "Bench restored"
}

show_status() {
  local state
  state="$(get_uwb_state)"
  printf 'UWB state: %s (%s)\n' "$(state_name "${state}")" "${state:-none}"
  if [[ "${state}" == "2" ]]; then
    print_data_sample
  fi
}

usage() {
  cat <<EOF
Usage:
  $0 start [TAG_NAME]  Pair Tag and start ranging
  $0 status            Show UWB state and one data sample
  $0 stop              Stop ranging and restore S100 VLN

Default Tag: ${DEFAULT_TAG_NAME}
EOF
}

main() {
  load_ros_env || return 1

  case "${1:-}" in
    start)
      start_ranging "${2:-${DEFAULT_TAG_NAME}}"
      ;;
    status)
      show_status
      ;;
    stop)
      stop_ranging
      ;;
    *)
      usage
      return 2
      ;;
  esac
}

main "$@"
