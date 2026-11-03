from pathlib import Path


def test_track_data_assets_exist():
    track_dir = Path(__file__).resolve().parents[1] / "frontend" / "public" / "track_data"

    assert track_dir.is_dir()
    assert (track_dir / "f1-25_silverstone.json").exists()
