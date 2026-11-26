import json
import pytest
from krem.coach.benchmarks import CornerBenchmark, TrackBenchmark
from krem.coach.comparator import classify_exit, compare_lap_to_benchmark
from krem.coach.gemini import build_coach_prompt, parse_coach_response


@pytest.mark.parametrize('delta, expected', [(None, 'unavailable'), (-50,'slow'), (-49.99,'on pace'), (0,'on pace'), (49.99,'on pace'), (50,'fast')])
def test_threshold(delta, expected):
    assert classify_exit(delta) == expected


def fixture():
    c = CornerBenchmark('1','Test',100,200,150,1,80,90,2,170,
        ideal_exit_speed_kph=200, optimal_brake_m=100, optimal_acceleration_start_m=160)
    return TrackBenchmark(0,'Test',1000,300,600,60000,[c])


def test_exit_and_pedal_crossings():
    samples = [dict(distance=d,speed=v,brake=b,throttle=t) for d,v,b,t in
        [(90,200,0,0),(110,190,.2,0),(140,80,.3,0),(160,100,0,.2),(190,140,0,.8),(210,160,0,1)]]
    result = compare_lap_to_benchmark(samples,fixture())[0]
    assert result.player_exit_speed_kph == 150
    assert result.classification == 'slow'
    assert result.player_brake_on_m == 110
    assert result.player_throttle_on_m == 160
    assert 'optimal' in build_coach_prompt(fixture(),60000,[result])
    samples[-1]['gapBefore'] = True
    assert compare_lap_to_benchmark(samples,fixture())[0].player_exit_speed_kph is None
    samples[-1]['gapBefore'] = False
    samples[-2]['speed'] = None
    assert compare_lap_to_benchmark(samples,fixture())[0].classification == 'unavailable'


def test_missing_targets_not_apex_substitution():
    track = fixture()
    track.corners[0].ideal_exit_speed_kph = None
    result = compare_lap_to_benchmark([{'distance':200,'speed':180}],track)[0]
    assert result.classification == 'unavailable'
    assert result.ideal_exit_speed_kph is None


@pytest.mark.parametrize('value', ['garbage','{}','[]','[{"turn":"2","advice":"x"}]',
    '[{"turn":"1","advice":""}]','[{"turn":1,"advice":"x"}]',
    '[{"turn":"1","advice":"x","extra":1}]'])
def test_bad_response_rejected(value):
    with pytest.raises(ValueError):
        parse_coach_response(value,['1'])


def test_response_matches_turns_and_order():
    data = [{'turn':'2','advice':' Second '},{'turn':'1','advice':'First'}]
    assert parse_coach_response(json.dumps(data),['1','2']) == [data[1],{'turn':'2','advice':'Second'}]
    with pytest.raises(ValueError):
        parse_coach_response(json.dumps([data[0],data[0]]),['1','2'])


def test_api_lap_validation_and_reference(monkeypatch):
    from fastapi.testclient import TestClient
    import krem.server as server
    class State:
        def snapshot(self):
            return {'session': {'trackId':0}, 'player':{}}
        def lap_history_snapshot(self):
            return [dict(lap=1,trackId=0,samples=[{'distance':200,'speed':200}],lapTimeMs=60000),
                    dict(lap=2,trackId=0,samples=[{'distance':200,'speed':150}],lapTimeMs=61000),
                    dict(lap=3,trackId=0,invalid=True)]
    monkeypatch.setattr(server.BenchmarkRegistry,'get_benchmark',lambda self, track_id: fixture())
    monkeypatch.setattr(server,'generate_coach_advice',lambda **kwargs: {'status':'ok','advice':[{'turn':'1','advice':'Test'}]})
    monkeypatch.setattr(server,'get_gemini_api_key',lambda: None)
    client = TestClient(server.create_app(State()))
    assert client.post('/api/coach/analyse',json={'lapNum':9}).status_code == 404
    assert client.post('/api/coach/analyse',json={'lapNum':3}).status_code == 422
    response = client.post('/api/coach/analyse',json={'lapNum':2,'referenceLapNum':1})
    assert response.status_code == 200, response.text
    assert response.json()['deltas'][0]['classification'] == 'slow'
    assert client.post('/api/coach/analyse',json={'lapNum':2,'referenceLapNum':2}).status_code == 422


@pytest.mark.parametrize('text,status', [('[{"turn":"1","advice":"Hold your exit speed."}]','ok'), ('not JSON','unavailable')])
def test_gemini_structured_contract(monkeypatch, text, status):
    from types import SimpleNamespace
    from google import genai
    from google.genai import types
    import krem.coach.gemini as gemini
    captured = {}
    def generate(**kwargs):
        captured.update(kwargs)
        types.GenerateContentConfig(**kwargs['config'])
        return SimpleNamespace(text=text)
    monkeypatch.setattr(gemini,'get_gemini_api_key',lambda: 'test-only')
    monkeypatch.setattr(genai,'Client',lambda **kwargs: SimpleNamespace(models=SimpleNamespace(generate_content=generate)))
    corners = compare_lap_to_benchmark([{'distance':200,'speed':150}],fixture())
    result = gemini.generate_coach_advice(fixture(),60000,corners)
    assert result['status'] == status
    assert captured['config']['response_mime_type'] == 'application/json'
    assert 'player_exit_speed_kph' in captured['contents']
    if status != 'ok':
        assert result['advice'] == []
