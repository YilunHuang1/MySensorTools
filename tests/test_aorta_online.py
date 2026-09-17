import importlib.util
from pathlib import Path
import sys

import pytest
from sensor_tools import aorta

SMOKE = Path(__file__).resolve().parents[1] / 'uwb/smoke_test'
sys.path.insert(0, str(SMOKE))
import checks_online as online
from report import CheckResult, CheckStatus, SmokeTestReport


def test_cli_flow_text_preserves_types_and_nested_braces():
    data = list(aorta.objects('banner\n--- Message 1 ---\n{state: IDLE, is_charging: false, value: 42, message: "brace } and \\" quote", versions: [{sw_version: "5.2.4"}]}'))[0]
    assert data['state'] == 'IDLE'
    assert data['is_charging'] is False
    assert data['versions'][0]['sw_version'] == '5.2.4'
    with pytest.raises(ValueError):
        list(aorta.objects('{broken: [1]'))


@pytest.mark.parametrize('status,expected,code', [(CheckStatus.PASS, 'PASS', 0), (CheckStatus.WARN, 'INCOMPLETE', 2), (CheckStatus.SKIP, 'INCOMPLETE', 2), (CheckStatus.FAIL, 'FAIL', 1)])
def test_report_does_not_pass_missing_coverage(status, expected, code):
    report = SmokeTestReport(results=[CheckResult('sample', status)])
    assert report.overall == expected
    assert report.exit_code == code
    assert SmokeTestReport().overall == 'INCOMPLETE'


def test_fault_query_requires_success(monkeypatch):
    monkeypatch.setattr(aorta, 'call', lambda *args: {'status': 'REJECTED', 'error_code': 0})
    assert online.check_error_status_online().status == CheckStatus.WARN
    monkeypatch.setattr(aorta, 'call', lambda *args: {'status': 'SUCCESS', 'error_code': 0})
    assert online.check_error_status_online().status == CheckStatus.PASS


def test_bad_version_does_not_pass(monkeypatch):
    monkeypatch.setattr(aorta, 'call', lambda *args: {'status': 'SUCCESS', 'versions': [{'name': 'uwb_anchor', 'sw_version': 'broken'}]})
    assert online.check_anchor_version_online()[0].status == CheckStatus.WARN


def test_rate_no_data_no_threshold_and_rollback():
    assert online.check_ranging_online(rows=[])[0].status == CheckStatus.WARN
    rows = [{'publish_time_ns': 1}, {'publish_time_ns': 50_000_001}]
    assert online.check_ranging_online(rows=rows)[1] == 20
    assert online.check_ranging_online(rows=rows)[0].status == CheckStatus.WARN
    assert online.check_ranging_online(rows=rows, min_frame_rate=12)[0].status == CheckStatus.PASS
    assert online.check_ranging_online(rows=rows[::-1])[0].status == CheckStatus.FAIL


def test_quality_counts_invalid_and_uses_circular_mean():
    rows = [dict(distance=1., distance_filtered=1., angle=a, angle_filtered=a, pitch=0, pos_confidence=90) for a in [179, -179]]
    result = online.check_data_quality_online(rows=rows)
    assert abs(result.data['circular_mean_angle']) == 180
    rows[0]['distance_filtered'] = float('nan')
    assert online.check_data_quality_online(rows=rows).status == CheckStatus.FAIL


@pytest.mark.parametrize('state', ['UNKNOWN', 99, True, None])
def test_unknown_connection_state_is_not_pass(monkeypatch, state):
    monkeypatch.setattr(online.aorta, 'echo', lambda *_: [{'state': state, 'battery_percentage': 50}])
    assert online.check_uwb_status_online().status == CheckStatus.WARN


def test_record_exact_topic_uses_group_and_suffix(monkeypatch, tmp_path):
    observed = []
    monkeypatch.setattr(aorta, 'command', lambda name, args: [name, *args])
    class Recorder:
        returncode = 0
        def __init__(self, args, **kwargs):
            observed.extend(args)
            Path(args[args.index('--output') + 1]).write_bytes(b'fixture')
        def communicate(self, timeout):
            return '', ''
    monkeypatch.setattr(aorta.subprocess, 'Popen', Recorder)
    aorta.capture(tmp_path/'out.mcap', ['aorta/bench/pub/imu_raw'], .5)
    assert observed[observed.index('--include') + 1] == 'imu_raw'
    assert observed[observed.index('--group') + 1] == 'bench'
    assert observed[observed.index('--duration') + 1] == '1'
    with pytest.raises(ValueError, match='mix Aorta groups'):
        aorta.capture(tmp_path/'mixed.mcap', ['aorta/a/pub/imu_raw', 'aorta/b/pub/imu_raw'])
