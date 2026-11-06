from unittest.mock import patch

from fastapi.testclient import TestClient

from krem.coach.benchmarks import CornerBenchmark, TrackBenchmark
from krem.coach.comparator import compare_lap_to_benchmark
from krem.coach.gemini import build_coach_prompt, clean_gemini_corner_advice
from krem.pipeline import LiveState, PlayerState
from krem.pipeline.sector_timing import SectorTiming
from krem.server import create_app
from krem.core import PacketId
from test_live_freshness import packet


def benchmark():
    return TrackBenchmark(10, 'Test track', 1000, 300, 700, 60000, [
        CornerBenchmark('1', 'Hairpin', 100, 200, 150, 2, 100, 100, 3, 175),
        CornerBenchmark('2', 'Missing corner', 400, 500, 450, 2, 400, 100, 3, 475),
        CornerBenchmark('3', 'Other sector', 800, 900, 850, 3, 800, 100, 3, 875),
    ])


def samples(brake_at=100, throttle_at=175):
    return [dict(distance=d, elapsedTimeMs=d * 10, speed=100, brake=float(brake_at <= d < 150),
                 throttle=float(d < 90 or d >= throttle_at), gapBefore=False)
            for d in range(0, 281, 5)]


def test_corner_input_timestamps_and_missing_corner_are_explicit():
    rows = compare_lap_to_benchmark(samples(), benchmark(), target_sector=2)
    assert [row.turn for row in rows] == ['1', '2']
    first = rows[0]
    assert (first.brake_on_ms, first.brake_release_ms, first.throttle_on_ms) == (1000, 1500, 1750)
    assert first.status == 'on_pace'
    assert rows[1].status == 'insufficient_data'
    assert rows[1].player_brake_on_m is None


def test_late_inputs_are_graded_from_inputs_not_estimated_time_loss():
    row = compare_lap_to_benchmark(samples(125, 200), benchmark(), 2)[0]
    assert row.brake_delta_m == -25
    assert row.throttle_delta_m == 25
    assert row.status == row.brake_status == row.throttle_status == 'late'


def test_missing_and_gapped_samples_cannot_be_on_pace():
    trace = samples()
    trace[25]['brake'] = None
    assert compare_lap_to_benchmark(trace, benchmark(), 2)[0].status == 'insufficient_data'
    trace = samples()
    trace[25]['gapBefore'] = True
    assert compare_lap_to_benchmark(trace, benchmark(), 2)[0].status == 'insufficient_data'


def test_prompt_contains_previous_lap_timing_and_only_upcoming_turns():
    rows = compare_lap_to_benchmark(samples(), benchmark())
    prompt = build_coach_prompt(benchmark(), 60000, rows, 2, 4)
    assert 'Evaluated lap: 4' in prompt and '"brake_on_ms": 1000' in prompt
    assert '"turn": "3"' not in prompt
    advice = clean_gemini_corner_advice('Turn 1: Hold the timing.\nTurn 99: Invented turn.', rows[:2])
    assert 'Turn 99' not in advice and 'Turn 2:' in advice


def test_sector_elapsed_and_grades():
    timing = SectorTiming()
    timing.history = {0: [(1, [30000, 40000, 20000])], 1: [(1, [29000, 38000, 19000])]}
    player = PlayerState(current_lap_num=2, sector=1, sector1_time_ms=29500, current_lap_time_ms=42000)
    result = timing.snapshot(player, 0, [])
    assert result[0]['timeMs'] == 29500 and result[0]['grade'] == 'green'
    assert result[1]['timeMs'] == 12500 and result[1]['grade'] == 'neutral'
    player.sector1_time_ms = 28500
    assert timing.snapshot(player, 0, [])[0]['grade'] == 'purple'
    player.sector1_time_ms = 30500
    assert timing.snapshot(player, 0, [])[0]['grade'] == 'yellow'
    player.sector = 2; player.sector2_time_ms = 39000; player.current_lap_time_ms = 80000
    assert timing.snapshot(player, 0, [])[2]['timeMs'] == 10500
    player.current_lap_invalid = 1
    assert timing.snapshot(player, 0, [])[0]['grade'] == 'neutral'


def test_first_lap_has_no_fabricated_sector_grade():
    result = SectorTiming().snapshot(PlayerState(current_lap_num=1, sector=1, sector1_time_ms=30000, current_lap_time_ms=31000), 0, [])
    assert result[0]['grade'] == 'neutral'
    assert result[1]['timeMs'] == 1000


def test_pace_is_independent_of_pedal_transitions():
    trace = samples()
    for s in trace:
        s['speed'] = 120
        s['throttle'] = .5
    row = compare_lap_to_benchmark(trace, benchmark(), 2)[0]
    assert row.pace_status == 'fast'
    assert row.throttle_on_ms is None
    for s in trace:
        s['speed'] = 80
    assert compare_lap_to_benchmark(trace, benchmark(), 2)[0].pace_status == 'slow'
    for s in trace:
        s['speed'] = 103
    assert compare_lap_to_benchmark(trace, benchmark(), 2)[0].pace_status == 'on_pace'
    trace[25]['gapBefore'] = True
    assert compare_lap_to_benchmark(trace, benchmark(), 2)[0].pace_status == 'insufficient_data'


def test_repeated_game_clock_does_not_invalidate_measured_corner():
    trace = samples()
    trace[25]['elapsedTimeMs'] = trace[24]['elapsedTimeMs']
    row = compare_lap_to_benchmark(trace, benchmark(), 2)[0]
    assert row.pace_status == 'on_pace'
    assert row.status != 'insufficient_data'


def test_constant_inputs_are_observations_not_missing_telemetry():
    trace = samples()
    for s in trace:
        s['throttle'] = .5
        s['brake'] = 0
    row = compare_lap_to_benchmark(trace, benchmark(), 2)[0]
    assert row.status != 'insufficient_data'
    assert row.brake_status == 'no_braking'
    assert row.throttle_status == 'held_below_85_percent'
    assert 'build power' in row.diagnosis


def test_damage_packet_reaches_all_hud_components():
    state = LiveState()
    damage = packet(PacketId.CAR_DAMAGE)
    damage.data['cars'] = damage.data['cars'].copy()
    car = damage.data['cars'][0]
    car['tyresDamage'] = [1, 10, 20, 60]
    car['floorDamage'] = 20
    car['rearWingDamage'] = 60
    state.update(damage)
    player = state.snapshot()['player']
    assert player['tyres']['damagePct'] == [1, 10, 20, 60]
    assert player['damage']['floorDamage'] == 20
    assert player['damage']['rearWingDamage'] == 60


def test_invalid_running_sector_is_not_graded():
    timing = SectorTiming()
    timing.history = {0: [(1, [10000, 20000, 30000])]}
    player = PlayerState(current_lap_num=2, sector=0, current_lap_time_ms=11000, current_lap_invalid=1)
    assert timing.snapshot(player, 0, [])[0]['grade'] == 'neutral'


def test_coach_key_request_is_read_from_json_body():
    with patch('krem.server.persist_gemini_api_key') as persist:
        with TestClient(create_app(LiveState())) as client:
            assert client.post('/api/coach/key', json={'apiKey': 'test-only-placeholder'}).status_code == 200
            persist.assert_called_once_with('test-only-placeholder')


def test_coach_api_uses_exact_previous_lap_and_upcoming_sector():
    state = LiveState()
    state.update(packet(PacketId.SESSION))
    state.update(packet(PacketId.LAP_DATA))
    state.session.track_id = 10
    state.player.current_lap_num = 3
    state.player.sector = 0
    state.lap_recorder.records.append(dict(lap=2, samples=samples(), lapTimeMs=60000))
    with patch('krem.server.BenchmarkRegistry.get_benchmark', return_value=benchmark()), \
         patch('krem.server.generate_coach_advice', return_value='Turn 1: Keep the timing.') as generate:
        with TestClient(create_app(state)) as client:
            data = client.post('/api/coach/analyse', json={'trackId': 10, 'lapNum': 2}).json()
            assert data['lapNum'] == 2 and data['nextSector'] == 2
            assert [c['turn'] for c in data['corners']] == ['1', '2']
            assert generate.call_args.kwargs['corner_deltas'][0].brake_on_ms == 1000
            assert client.post('/api/coach/analyse', json={'lapNum': 1}).status_code == 409
            state.player.current_lap_num = 4
            assert client.post('/api/coach/analyse', json={}).status_code == 409
