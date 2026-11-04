"""Pause retention must not make stale data fresh or create driving samples."""
from dataclasses import replace
from unittest.mock import patch

from krem.core import PacketId
from krem.pipeline import LiveState
from test_live_freshness import packet


def telemetry(frame=1, speed=200):
    p = packet(PacketId.CAR_TELEMETRY)
    p.header = replace(p.header, frame_identifier=frame, overall_frame_identifier=frame, session_time=float(frame))
    p.data['cars'] = p.data['cars'].copy()
    car = p.data['cars'][0]
    car['speed'], car['throttle'], car['brake'] = speed, 1, .5
    car['tyresSurfaceTemperature'] = [80,81,82,83]
    return p


def session(paused):
    p = packet(PacketId.SESSION)
    p.data['gamePaused'] = int(paused)
    return p


def test_pause_retains_values_without_recording_repeats():
    state = LiveState()
    with patch('krem.pipeline.time.monotonic', return_value=10):
        state.update(session(False));state.update(telemetry())
        before=state.snapshot()
        state.update(session(True))
        pending=len(state.lap_recorder.pending)
        state.update(telemetry(2, 0))
        assert len(state.lap_recorder.pending)==pending
    with patch('krem.pipeline.time.monotonic', return_value=20):
        state.update(session(True))
        snap=state.snapshot()
        assert snap['gamePaused'] is True
        assert snap['retainedLive']['player']['speed']==200
        assert snap['retainedLive']['player']['throttle']==1
        assert snap['retainedLive']['player']['brake']==.5
        assert snap['retainedLive']['player']['tyres']['surfaceTempC']==[80,81,82,83]
        assert snap['player']['speed'] is None
        assert snap['freshness']['telemetry']['state']=='stale'
        assert snap['telemetrySample']==before['telemetrySample']
        assert snap['liveStreamId']==before['liveStreamId']


def test_resume_requires_new_telemetry_and_then_updates():
    state=LiveState()
    with patch('krem.pipeline.time.monotonic', return_value=10):
        state.update(telemetry());state.update(session(True))
    with patch('krem.pipeline.time.monotonic', return_value=20):
        state.update(session(False))
        snap=state.snapshot()
        assert not snap['gamePaused'] and snap['player']['speed'] is None
        state.update(telemetry(2,220));snap=state.snapshot()
        assert snap['player']['speed']==220
        assert snap['telemetrySample']['sessionTime']==2


def test_silence_is_stale_not_pause_and_retains_data():
    state=LiveState()
    with patch('krem.pipeline.time.monotonic', return_value=10):state.update(telemetry())
    with patch('krem.pipeline.time.monotonic', return_value=30):
        snap=state.snapshot()
        assert not snap['gamePaused']
        assert snap['retainedLive']['player']['speed']==200
        assert snap['freshness']['telemetry']['state']=='stale'


def test_never_received_fields_stay_missing():
    state=LiveState();state.update(session(True));snap=state.snapshot()
    assert snap['retainedLive']['player']['speed'] is None
    assert snap['retainedLive']['player']['damage']['floorDamage'] is None
    assert snap['telemetrySample'] is None


def test_new_session_does_not_retain_old_paused_car():
    state=LiveState();state.update(telemetry());state.update(session(True))
    old=state.snapshot()['liveStreamId']
    state.update(packet(PacketId.SESSION,uid=2));snap=state.snapshot()
    assert not snap['gamePaused']
    assert snap['liveStreamId']!=old
    assert snap['retainedLive']['player']['speed'] is None


def test_unrelated_packets_do_not_advance_sample_identity():
    state=LiveState();state.update(telemetry());before=state.snapshot()['telemetrySample']
    state.update(packet(PacketId.CAR_DAMAGE));state.update(session(False))
    assert state.snapshot()['telemetrySample']==before
