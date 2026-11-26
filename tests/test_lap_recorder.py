"""Synthetic coverage for exact-frame lap recording."""
import struct
from dataclasses import replace
from unittest.mock import patch
import numpy as np
import pytest
from krem.core import PACKET_FORMAT, GAME_YEAR, PACKET_SIZES, PacketId
from krem.ingest import decode_packet, DT_LAP_HISTORY
from krem.pipeline import LiveState
from krem.pipeline.lap_recorder import LapRecorder


def make(pid, frame, uid=2**60+123, player=0, at=None):
    header=struct.pack('<HBBBBBQfIIBB',PACKET_FORMAT,GAME_YEAR,1,0,1,pid,uid,
                       frame/60 if at is None else at,frame,frame,player,255)
    p=decode_packet(header+bytes(PACKET_SIZES[pid]-len(header)))
    if 'cars' in p.data:p.data['cars']=p.data['cars'].copy()
    return p


def pair(frame,lap=1,elapsed=0,distance=0,invalid=0,last=0,at=None,uid=2**60+123):
    p=make(PacketId.LAP_DATA,frame,uid=uid,at=at);c=p.data['cars'][0]
    c['currentLapNum'],c['currentLapTimeInMS'],c['lapDistance']=lap,elapsed,distance
    c['currentLapInvalid'],c['lastLapTimeInMS'],c['driverStatus']=invalid,last,1
    c['sector1TimeMSPart']=200 if elapsed>=200 else 0
    c['sector2TimeMSPart']=200 if elapsed>=400 else 0
    t=make(PacketId.CAR_TELEMETRY,frame,uid=uid,at=at)
    t.data['cars'][0]['speed']=180;t.data['cars'][0]['throttle']=1.0
    return p,t


def recorder():
    r=LapRecorder();s=make(PacketId.SESSION,0)
    s.data['trackId']=0;s.data['trackLength']=100;r.ingest(s);return r


def add(r,packets):
    for p in packets:r.ingest(p)


def completed(r,missing=False,invalid=False,start=0):
    for i in range(start,6):
        ps=pair(i+1,elapsed=i*100,distance=i*18,invalid=int(invalid and i==2))
        add(r,ps[:1] if missing and i==2 else ps)
    add(r,pair(7,lap=2,last=600));r.flush(force=True);return r.records[-1]


def test_complete_lap_preserves_splits_and_exact_ids():
    r=recorder();lap=completed(r)
    assert lap['lapTimeMs']==600
    assert [lap[f'sector{i}TimeMs'] for i in (1,2,3)]==[200,200,200]
    assert not lap['partial'] and not lap['invalid']
    assert lap['sampleCount']==6 and lap['avgThrottle']==1
    assert lap['samples'][-1]['elapsedTimeMs']==500
    assert lap['samples'][0]['sessionUid']==str(2**60+123)
    assert r.current['lap']==2


def test_reordered_packets_and_duplicates():
    r=recorder();frames=[pair(i+1,elapsed=i*100,distance=i*18) for i in range(6)]
    for i in [1,0,3,2,5,4]:
        p,t=frames[i];add(r,[t,t,p,p])
    add(r,pair(7,lap=2,last=600));r.flush(force=True)
    assert [s['overallFrameId'] for s in r.records[0]['samples']]==list(range(1,7))
    add(r,frames[0]);r.flush(force=True)
    assert len(r.records[0]['samples'])==6


def test_missing_packet_is_null_not_previous_input():
    lap=completed(recorder(),missing=True)
    assert lap['samples'][2]['throttle'] is None
    assert lap['partial'] and 'missing_telemetry' in lap['qualityReasons']


@pytest.mark.parametrize('mismatch',['frame','time'])
def test_alignment_rejects_wrong_frame_or_time(mismatch):
    r=recorder();p,t=pair(1)
    if mismatch=='frame':t.header=replace(t.header,frame_identifier=999)
    else:t.header=replace(t.header,session_time=t.header.session_time+0.1)
    add(r,[p,t]);r.flush(force=True)
    assert r.current['samples'][0]['speed'] is None


def test_partial_start_and_invalid_are_sticky():
    lap=completed(recorder(),invalid=True,start=2)
    assert lap['invalid'] and lap['partial'] and 'partial_start' in lap['qualityReasons']


def test_skipped_boundary_has_no_invented_lap_time():
    r=recorder();add(r,pair(1));add(r,pair(2,lap=3,last=600));r.flush(force=True)
    assert r.records[0]['lapTimeMs'] is None
    assert 'skipped_lap_boundary' in r.records[0]['qualityReasons']


def test_missing_time_and_reverse_distance_break_trace():
    r=recorder();add(r,pair(1));add(r,pair(2,elapsed=400,distance=50))
    add(r,pair(3,elapsed=450,distance=40));r.flush(force=True)
    assert r.current['samples'][1]['gapBefore'] and r.current['samples'][2]['gapBefore']
    assert 'non_monotonic_distance' in r.current['reasons']


def test_flashback_event_clears_timeline_once():
    r=recorder();completed(r);epoch=r.epoch
    e=make(PacketId.EVENT,10);e.data={'code':'FLBK'};r.ingest(e);r.ingest(e)
    assert r.epoch==epoch+1 and not r.records and not r.pending
    add(r,pair(11,elapsed=300,distance=50,at=0.02));r.flush(force=True)
    assert 'partial_start' in r.current['reasons']


def test_implicit_rewind_clears_old_laps():
    r=recorder();completed(r);epoch=r.epoch
    add(r,pair(8,lap=1,elapsed=100,distance=10,at=0.01));r.flush(force=True)
    assert not r.records and r.epoch==epoch+1


def test_session_and_player_reset():
    r=recorder();completed(r);epoch=r.epoch
    add(r,pair(1,uid=99));r.flush(force=True)
    assert not r.records and r.epoch==epoch+1 and r.identity==(99,0)
    r.ingest(make(PacketId.CAR_TELEMETRY,2,uid=99,player=1))
    assert r.current is None and r.identity==(99,1)


def test_history_repairs_splits_and_validity():
    r=recorder();completed(r);p=make(PacketId.SESSION_HISTORY,20)
    rows=np.zeros(100,dtype=DT_LAP_HISTORY);rows[0]['lapTimeInMS']=610
    for i,v in enumerate([201,202,207],1):rows[0][f'sector{i}TimeMSPart']=v
    rows[0]['lapValidBitFlags']=14
    p.data={'carIdx':0,'numLaps':1,'lapHistoryData':rows};r.ingest(p)
    assert r.records[0]['invalid'] and r.records[0]['sector3TimeMs']==207


def test_age_flush_does_not_finalize_unfinished_lap():
    r=recorder()
    with patch('krem.pipeline.lap_recorder.time.monotonic',return_value=10):add(r,pair(1))
    assert r.current is None
    with patch('krem.pipeline.lap_recorder.time.monotonic',return_value=10.3):r.flush()
    assert r.current['samples'] and not r.records


def test_bounded_buffer_and_live_state_integration():
    state=LiveState()
    for i in range(1,100):
        for p in pair(i,elapsed=i*16,distance=i):state.update(p)
    assert len(state.lap_recorder.pending)<=9
    snap=state.snapshot()
    assert snap['recorder']['currentSampleCount']>0 and snap['laps']==[]
    assert state.lap_history_snapshot()==[]


def test_sample_limit_is_explicit():
    r=recorder();r.MAX_SAMPLES=2
    for i in range(4):add(r,pair(i+1,elapsed=i*100,distance=i*18))
    r.flush(force=True)
    assert len(r.current['samples'])==2 and 'sample_limit' in r.current['reasons']


def test_invalid_input_is_not_recorded_as_real_zero():
    r=recorder();p,t=pair(1);t.data['cars'][0]['throttle']=float('nan')
    add(r,[p,t]);r.flush(force=True)
    assert r.current['samples'][0]['throttle'] is None
    assert 'missing_telemetry' in r.current['reasons']


def test_incomplete_end_and_pit_lap_are_labelled():
    r=recorder();p,t=pair(1);p.data['cars'][0]['pitStatus']=1
    add(r,[p,t]);add(r,pair(2,lap=2,last=1000));r.flush(force=True)
    assert {'partial_end','pit_or_out_lap'} <= set(r.records[0]['qualityReasons'])


def test_other_car_history_is_ignored():
    r=recorder();completed(r);p=make(PacketId.SESSION_HISTORY,20)
    p.data['carIdx']=1;r.ingest(p)
    assert r.history_packet is None


def test_both_missing_packets_produce_a_gap_on_next_sample():
    r=recorder();add(r,pair(1));add(r,pair(30,elapsed=500,distance=90))
    add(r,pair(31,lap=2,last=600));r.flush(force=True)
    assert r.records[0]['samples'][-1]['gapBefore']
    assert r.records[0]['partial']


def test_sample_captures_gear_steer_rpm_drs():
    r = recorder()
    p, t = pair(1, lap=1, elapsed=100, distance=15)
    t.data['cars'][0]['gear'] = 4
    t.data['cars'][0]['steer'] = -0.35
    t.data['cars'][0]['engineRPM'] = 11200
    t.data['cars'][0]['drs'] = 1
    add(r, [p, t])
    r.flush(force=True)
    sample = r.current['samples'][0]
    assert sample['gear'] == 4
    assert sample['steer'] == pytest.approx(-0.35, rel=1e-3)
    assert sample['steering'] == pytest.approx(-0.35, rel=1e-3)
    assert sample['rpm'] == 11200
    assert sample['drs'] == 1


def test_current_lap_snapshot():
    r = recorder()
    assert r.current_lap_snapshot() is None
    p, t = pair(1, lap=2, elapsed=450, distance=80)
    add(r, [p, t])
    r.flush(force=True)
    snapshot = r.current_lap_snapshot()
    assert snapshot is not None
    assert snapshot['lap'] == 2
    assert snapshot['inProgress'] is True
    assert len(snapshot['samples']) == 1


def test_mid_lap_damage_change_only_affects_samples_from_that_point():
    r = recorder()
    # Frame 1: intact car
    p1, t1 = pair(1, elapsed=0, distance=0)
    d1 = make(PacketId.CAR_DAMAGE, 1)
    d1.data['cars'][0]['frontLeftWingDamage'] = 0
    d1.data['cars'][0]['tyresWear'] = np.array([5.0, 5.0, 5.0, 5.0], dtype=np.float32)
    add(r, [p1, t1, d1])

    # Frame 2: still intact
    p2, t2 = pair(2, elapsed=100, distance=18)
    add(r, [p2, t2])

    # Frame 3: damage occurs (front wing hit 35%, tyre wear 12%)
    p3, t3 = pair(3, elapsed=200, distance=36)
    d3 = make(PacketId.CAR_DAMAGE, 3)
    d3.data['cars'][0]['frontLeftWingDamage'] = 35
    d3.data['cars'][0]['tyresWear'] = np.array([12.0, 5.0, 5.0, 5.0], dtype=np.float32)
    add(r, [d3, p3, t3])

    # Finish lap
    add(r, pair(4, lap=2, last=300))
    r.flush(force=True)

    lap = r.records[-1]
    samples = lap['samples']
    assert len(samples) == 3

    # Frame 1 & 2 before the hit have 0 wing damage
    assert samples[0]['damage']['frontLeftWingDamage'] == 0
    assert samples[1]['damage']['frontLeftWingDamage'] == 0
    assert samples[0]['tyres']['wearPct'][0] == 5.0
    assert samples[1]['tyres']['wearPct'][0] == 5.0

    # Frame 3 at the hit has 35% wing damage and 12% tyre wear
    assert samples[2]['damage']['frontLeftWingDamage'] == 35
    assert samples[2]['tyres']['wearPct'][0] == 12.0


def test_lap_samples_record_car_position_per_frame():
    r = recorder()
    p1, t1 = pair(1, lap=1, elapsed=0, distance=0)
    p1.data['cars'][0]['carPosition'] = 3
    p2, t2 = pair(2, lap=1, elapsed=100, distance=18)
    p2.data['cars'][0]['carPosition'] = 0  # unset / invalid position
    add(r, [p1, t1, p2, t2])

    p3, t3 = pair(3, lap=2, elapsed=0, distance=0, last=200)
    p3.data['cars'][0]['carPosition'] = 4
    add(r, [p3, t3])
    r.flush(force=True)

    assert len(r.records) == 1
    lap1_samples = r.records[0]['samples']
    assert lap1_samples[0]['position'] == 3
    assert lap1_samples[1]['position'] is None
    assert r.current['samples'][0]['position'] == 4


def test_lap_samples_record_all_player_values():
    r = recorder()
    p1, t1 = pair(1, lap=1, elapsed=0, distance=0)
    p1.data['cars'][0]['sector'] = 1
    t1.data['cars'][0]['gear'] = 6
    t1.data['cars'][0]['engineRPM'] = 11400
    t1.data['cars'][0]['drs'] = 1
    t1.data['suggestedGear'] = 7

    s1 = make(PacketId.CAR_STATUS, 1)
    s1.data['cars'][0]['drsAllowed'] = 1
    s1.data['cars'][0]['ersStoreEnergy'] = 2_450_000.0
    s1.data['cars'][0]['ersDeployMode'] = 3
    s1.data['cars'][0]['fuelInTank'] = 34.25
    s1.data['cars'][0]['fuelRemainingLaps'] = 12.6

    m1 = make(PacketId.MOTION, 1)
    m1.data['cars'][0]['gForceLateral'] = -1.85
    m1.data['cars'][0]['gForceLongitudinal'] = 2.4

    add(r, [s1, m1, p1, t1])
    add(r, pair(2, lap=2, last=200))
    r.flush(force=True)

    sample = r.records[0]['samples'][0]
    assert sample['sector'] == 1
    assert sample['gear'] == 6
    assert sample['rpm'] == 11400
    assert sample['drs'] == 1
    assert sample['drsAllowed'] == 1
    assert sample['suggestedGear'] == 7
    assert sample['gLat'] == pytest.approx(-1.85)
    assert sample['gLong'] == pytest.approx(2.4)
    assert sample['ersStore'] == 2_450_000.0
    assert sample['ersMode'] == 3
    assert sample['fuel'] == pytest.approx(34.25)
    assert sample['fuelLaps'] == pytest.approx(12.6)


def test_sector_crossing_clock_snap_does_not_wipe_lap():
    r = recorder()
    epoch = r.epoch
    add(r, pair(1, lap=1, elapsed=0, distance=0, at=0.0))
    add(r, pair(2, lap=1, elapsed=39249, distance=35, at=39.250))
    # Simulate F1 25 sector-split snap (-12 ms) while session_time and distance advance
    add(r, pair(3, lap=1, elapsed=39237, distance=40, at=39.261))
    add(r, pair(4, lap=1, elapsed=39270, distance=95, at=39.283))
    add(r, pair(5, lap=2, elapsed=10, distance=2, last=60000, at=60.0))
    r.flush(force=True)

    assert r.epoch == epoch
    assert len(r.records) == 1
    lap1 = r.records[0]
    assert [s['distance'] for s in lap1['samples']] == [0, 35, 40, 95]
    assert [s['elapsedTimeMs'] for s in lap1['samples']] == [0, 39249, 39249, 39270]
    assert 'partial_start' not in lap1['qualityReasons']

    # Real rewind (>50 ms backward on same lap) still invalidates
    r2 = recorder()
    epoch2 = r2.epoch
    add(r2, pair(1, lap=1, elapsed=0, distance=0, at=0.0))
    add(r2, pair(2, lap=1, elapsed=5000, distance=50, at=5.0))
    add(r2, pair(3, lap=1, elapsed=4000, distance=30, at=5.01))
    r2.flush(force=True)
    assert r2.epoch == epoch2 + 1
