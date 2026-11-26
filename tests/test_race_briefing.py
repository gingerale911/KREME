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


def samples(speed=100, profile=None):
    rows = []
    for d in range(0, 281, 5):
        s = profile(d) if profile is not None else speed
        rows.append(dict(distance=d, elapsedTimeMs=d * 10, speed=s, gapBefore=False))
    return rows


def test_corner_apex_range_and_missing_corner_are_explicit():
    rows = compare_lap_to_benchmark(samples(), benchmark(), target_sector=2)
    assert [row.turn for row in rows] == ['1', '2']
    first = rows[0]
    assert first.player_min_speed_kph == 100
    assert first.target_min_speed_kph == 80.0
    assert first.target_max_speed_kph == 120.0
    assert first.speed_buffer_kph == 20.0
    assert first.status == 'on_pace'
    assert first.pace_status == 'on_pace'
    assert rows[1].status == 'insufficient_data'
    assert rows[1].min_speed_m is None


def test_apex_speed_uses_20kph_target_range():
    # Braking corner hitting min speed right at apex_m=150
    def v_profile(min_spd):
        return lambda d: 140 - (140 - min_spd) * max(0.0, 1.0 - abs(d - 150) / 50.0)

    within = compare_lap_to_benchmark(samples(profile=v_profile(85)), benchmark(), 2)[0]
    assert within.min_speed_m == 150
    assert within.status == 'on_pace'
    assert within.pace_status == 'on_pace'

    boundary = compare_lap_to_benchmark(samples(profile=v_profile(80)), benchmark(), 2)[0]
    assert boundary.status == 'on_pace'

    too_slow = compare_lap_to_benchmark(samples(profile=v_profile(79)), benchmark(), 2)[0]
    assert too_slow.pace_status == 'slow'
    assert too_slow.status == 'below_target'

    fast = compare_lap_to_benchmark(samples(profile=v_profile(125)), benchmark(), 2)[0]
    assert fast.status == 'on_pace'
    assert fast.pace_status == 'fast'


def test_missing_and_gapped_samples_cannot_be_on_pace():
    trace = samples()
    trace[25]['speed'] = None
    assert compare_lap_to_benchmark(trace, benchmark(), 2)[0].status == 'insufficient_data'
    trace = samples()
    trace[25]['gapBefore'] = True
    assert compare_lap_to_benchmark(trace, benchmark(), 2)[0].status == 'insufficient_data'


def test_prompt_contains_apex_range_and_only_upcoming_turns():
    rows = compare_lap_to_benchmark(samples(speed=45), benchmark())
    prompt = build_coach_prompt(benchmark(), 60000, rows, 2, 4)
    assert 'Evaluated lap: 4' in prompt and '"player_min_speed_kph": 45.0' in prompt
    assert '"target_min_speed_kph": 80.0' in prompt
    assert '"turn": "3"' not in prompt
    advice = clean_gemini_corner_advice('Turn 1: Carry more apex speed.\nTurn 99: Invented turn.', rows[:2])
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


def test_apex_overshoot_early_flat_out_and_double_slowdown():
    # Manageable overshoot within +15 m (min at 165 m vs 150 m apex) -> on_pace
    ok_late = samples(profile=lambda d: 140 - 40 * max(0.0, 1.0 - abs(d - 165) / 50.0))
    assert compare_lap_to_benchmark(ok_late, benchmark(), 2)[0].status == 'on_pace'

    # Overshot beyond +15 m (min at 175 m vs 150 m apex, even though speed at 150 m is 120) -> late
    overshot = samples(profile=lambda d: 140 - 40 * max(0.0, 1.0 - abs(d - 175) / 50.0))
    row_late = compare_lap_to_benchmark(overshot, benchmark(), 2)[0]
    assert row_late.min_speed_m == 175
    assert row_late.status == 'late'
    assert row_late.pace_status == 'overshot'

    # Early minimum on a braking corner (min at 120 m vs 150 m apex, > 20 m early) -> early
    early = samples(profile=lambda d: 140 - 40 * max(0.0, 1.0 - abs(d - 120) / 30.0))
    row_early = compare_lap_to_benchmark(early, benchmark(), 2)[0]
    assert row_early.min_speed_m == 120
    assert row_early.status == 'early'

    # Flat-out accelerating sweep (min naturally at start_m=100) must NOT trigger early
    flat_out = samples(profile=lambda d: 90 + (d - 100) * 0.5)
    row_flat = compare_lap_to_benchmark(flat_out, benchmark(), 2)[0]
    assert row_flat.is_braking_corner is False
    assert row_flat.status == 'on_pace'

    # Slow early (90 at 120m) -> accelerate at apex (115 at 150m) -> slow again within +15m (85 at 160m)
    def double_dip(d):
        if d <= 120:
            return 140 - (d - 100) * 2.5
        if d <= 150:
            return 90 + (d - 120) * (25.0 / 30.0)
        if d <= 160:
            return 115 - (d - 150) * 3.0
        return 85 + (d - 160) * 1.5

    row_double = compare_lap_to_benchmark(samples(profile=double_dip), benchmark(), 2)[0]
    assert row_double.double_slowdown is True
    assert row_double.status == 'double_slowdown'


def test_benchmarks_exclude_straight_sections():
    from pathlib import Path
    from krem.coach.benchmarks import generate_benchmark_for_track

    track_dir = Path(__file__).resolve().parents[1] / "frontend" / "public" / "track_data"
    spa = generate_benchmark_for_track(10, track_dir)
    names = {c.name for c in spa.corners}
    assert "Kemmel" not in names
    assert "Pit Straight" not in names


def test_repeated_game_clock_does_not_invalidate_measured_corner():
    trace = samples()
    trace[25]['elapsedTimeMs'] = trace[24]['elapsedTimeMs']
    row = compare_lap_to_benchmark(trace, benchmark(), 2)[0]
    assert row.pace_status == 'on_pace'
    assert row.status != 'insufficient_data'


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
            assert data['corners'][0]['start_m'] == 100 and data['corners'][0]['end_m'] == 200
            assert data['corners'][0]['player_min_speed_kph'] == 100.0
            assert data['corners'][0]['target_min_speed_kph'] == 80.0
            assert data['corners'][0]['target_max_speed_kph'] == 120.0
            assert data['corners'][0]['speed_buffer_kph'] == 20.0
            assert generate.call_args.kwargs['corner_deltas'][0].player_min_speed_kph == 100.0
            assert client.post('/api/coach/analyse', json={'lapNum': 1}).status_code == 409
            state.player.current_lap_num = 4
            assert client.post('/api/coach/analyse', json={}).status_code == 409
