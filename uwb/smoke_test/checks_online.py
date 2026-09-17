"""Passive Aorta checks. Missing samples never constitute a passing measurement."""
import math
import re
import statistics
import subprocess
import tempfile
from pathlib import Path

from sensor_tools import aorta
from sensor_tools.uwb import iter_uwb_rows
from protocol import MIN_ANCHOR_VERSION, MIN_TAG_VERSION
from report import CheckResult, CheckStatus

ERRORS = (OSError, ValueError, RuntimeError, subprocess.TimeoutExpired)


def _version(name, device, minimum):
    try:
        response = aorta.call('firmware_version/uwb', {'target_device_type': 3})
        if response.get('status') != 'SUCCESS':
            raise ValueError(f"service did not succeed: {response.get('message', response)}")
        versions = [v.get('sw_version') for v in response.get('versions', []) if v.get('name') == device]
        if len(versions) != 1 or not re.fullmatch(r'\d+\.\d+\.\d+', versions[0] or ''):
            raise ValueError(f'{device}: version missing or malformed: {versions}')
        version = versions[0]
        status = CheckStatus.PASS if tuple(map(int, version.split('.'))) >= minimum else CheckStatus.FAIL
        return CheckResult(name, status, version, {'version': version}), version
    except ERRORS as error:
        return CheckResult(name, CheckStatus.WARN, str(error)), None


def check_anchor_version_online():
    return _version('Anchor 版本', 'uwb_anchor', MIN_ANCHOR_VERSION)


def check_tag_version_online():
    return _version('Tag 版本', 'uwb_tag', MIN_TAG_VERSION)


def check_uwb_status_online():
    try:
        data = aorta.echo('uwb/state')[0]
        state, battery = data.get('state'), data.get('battery_percentage')
        valid = isinstance(battery, (float, int)) and not isinstance(battery, bool) and 0 <= battery <= 100
        connected = not isinstance(state, bool) and state in ('CONNECTED', 'RANGING', 1, 2)
        status = CheckStatus.PASS if valid and battery >= 10 and connected else CheckStatus.WARN
        return CheckResult('Tag 状态/电量', status,
                           f"状态 {state}; 电量 {battery}%; 充电 {data.get('is_charging')}", data)
    except ERRORS as error:
        return CheckResult('Tag 状态/电量', CheckStatus.WARN, str(error))


def collect_ranging(duration):
    with tempfile.TemporaryDirectory(prefix='uwb-smoke-') as directory:
        path = Path(directory) / 'ranging.mcap'
        aorta.capture(path, ['uwb/ranging'], duration)
        return list(iter_uwb_rows(path, 'uwb/ranging'))


def check_ranging_online(duration=10, *, rows=None, min_frame_rate=18.0, state_before=None, state_after=None):
    try:
        rows = collect_ranging(duration) if rows is None else rows
        stamps = [r['publish_time_ns'] for r in rows]
        if not stamps:
            data = {'frame_count': 0, 'state_before': state_before, 'state_after': state_after}
            # Two snapshots distinguish an unmet test precondition from a broken data path.
            known_states = not isinstance(state_before, bool) and not isinstance(state_after, bool)
            if known_states and state_before in ('CONNECTED', 1) and state_after in ('CONNECTED', 1):
                return CheckResult('测距功能', CheckStatus.SKIP,
                                   '采集前后均为 CONNECTED：已连接但未开启测距；online 不发送开启命令', data), None
            if known_states and state_before in ('RANGING', 2) and state_after in ('RANGING', 2):
                return CheckResult('测距功能', CheckStatus.FAIL,
                                   '采集前后均为 RANGING，但 uwb/ranging 收到 0 帧；需检查数据发布/订阅链路', data), None
            return CheckResult('测距功能', CheckStatus.WARN,
                               f'收到 0 帧；测距状态未确认或发生变化 ({state_before} → {state_after})', data), None
        if len(stamps) < 2:
            return CheckResult('测距功能', CheckStatus.WARN, f'仅 {len(stamps)} 帧，未完成测距验收'), None
        if any(b <= a for a, b in zip(stamps, stamps[1:])):
            return CheckResult('测距功能', CheckStatus.FAIL, '发布时钟重复或回退，无法计算帧率'), None
        hz = (len(stamps) - 1) * 1e9 / (stamps[-1] - stamps[0])
        if min_frame_rate is None:
            status, reason = CheckStatus.WARN, '未指定部署配置的最低帧率，仅报告测量值'
        else:
            status = CheckStatus.PASS if hz >= min_frame_rate else CheckStatus.FAIL
            reason = f'最低要求 {min_frame_rate:g} Hz'
        return CheckResult('测距功能', status, f'{len(stamps)} 帧，{hz:.2f} Hz; {reason}',
                           {'frame_count': len(stamps), 'frame_rate': hz, 'min_frame_rate': min_frame_rate}), hz
    except ERRORS as error:
        return CheckResult('测距功能', CheckStatus.WARN, str(error)), None


def check_data_quality_online(duration=5, *, rows=None):
    try:
        rows = collect_ranging(duration) if rows is None else rows
        if not rows:
            return CheckResult('数据完整性', CheckStatus.SKIP, '无测距数据')
        invalid = []
        for index, row in enumerate(rows):
            fields = [row.get(k) for k in ('distance', 'angle', 'pitch', 'distance_filtered', 'angle_filtered', 'pos_confidence')]
            if (not all(isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v) for v in fields)
                    or row['distance'] <= 0 or row['distance_filtered'] <= 0):
                invalid.append(index)
        if invalid:
            return CheckResult('数据完整性', CheckStatus.FAIL, f'{len(rows)} 帧中 {len(invalid)} 帧字段无效',
                               {'invalid_indices': invalid, 'frame_count': len(rows)})
        distances = [r['distance_filtered'] for r in rows]
        angles = [math.radians(r['angle_filtered']) for r in rows]
        sine, cosine = sum(map(math.sin, angles)), sum(map(math.cos, angles))
        mean_angle = math.degrees(math.atan2(sine, cosine)) if math.hypot(sine, cosine) > 1e-9 else None
        data = {'frame_count': len(rows), 'avg_distance': statistics.mean(distances),
                'circular_mean_angle': mean_angle, 'avg_confidence': statistics.mean(r['pos_confidence'] for r in rows),
                'distance_std': statistics.stdev(distances) if len(rows) > 1 else None}
        # Without a measured target and motion condition, spread is not an accuracy test.
        return CheckResult('数据完整性', CheckStatus.PASS, f'{len(rows)} 帧字段有效；未验证定位精度', data)
    except ERRORS as error:
        return CheckResult('数据完整性', CheckStatus.WARN, str(error))


def check_error_status_online(*, capture_started_ns=None, ranging_passed=False):
    try:
        response = aorta.call('software/faultmgr/get_faults_info', {'type': 3, 'fault_list': []})
        if response.get('status') != 'SUCCESS' or response.get('error_code') != 0:
            raise ValueError(f'FaultMgr 查询未成功: {response}')
        # Empty FlatBuffers vectors can be omitted by the CLI; accept only after success.
        faults = response.get('fault_info_array') or []
        if not isinstance(faults, list) or any(not isinstance(f, dict) for f in faults):
            raise ValueError('malformed fault_info_array')
        blocking, non_blocking = [], []
        for fault in faults:
            stamp = fault.get('timestamp_ns')
            # A restarted UWB process can leave an old timeout latched in FaultMgr.
            # Only this known fault can be superseded by a successful current sample.
            if (ranging_passed and fault.get('fault_id') == 0x40060102
                    and type(stamp) is int and type(capture_started_ns) is int
                    and 0 < stamp < capture_started_ns):
                non_blocking.append(fault)
            else:
                blocking.append(fault)
        status = CheckStatus.WARN if blocking else CheckStatus.PASS
        detail = f'影响本轮结果的故障 {len(blocking)} 条（系统全量，非仅 UWB）'
        if non_blocking:
            detail += f'；{len(non_blocking)} 条采集前 UWB 超时记录，本轮测距通过，仅供参考'
        return CheckResult('系统当前故障', status, detail,
                           {'confirmed_current_snapshot': True, 'faults': faults,
                            'blocking_faults': blocking, 'non_blocking_faults': non_blocking,
                            'capture_started_ns': capture_started_ns,
                            'ranging_passed': ranging_passed})
    except ERRORS as error:
        return CheckResult('系统当前故障', CheckStatus.WARN, str(error), {'confirmed_current_snapshot': False})
