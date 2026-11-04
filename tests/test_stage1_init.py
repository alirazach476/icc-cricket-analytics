"""Stage 1 initialization tests — actually exercised in Stage 1."""

from pathlib import Path

from src.utils.config import get_project_root, get_settings, load_source_rules, load_tournaments
from src.utils.helpers import utc_now_iso


EXPECTED_TOURNAMENT_IDS = {
    "ODI_M_2003",
    "ODI_M_2007",
    "ODI_M_2011",
    "ODI_M_2015",
    "ODI_M_2019",
    "ODI_M_2023",
    "T20_M_2007",
    "T20_M_2009",
    "T20_M_2010",
    "T20_M_2012",
    "T20_M_2014",
    "T20_M_2016",
    "T20_M_2021",
    "T20_M_2022",
    "T20_M_2024",
    "T20_M_2026",
}


def test_project_root_contains_config_and_src() -> None:
    root = get_project_root()
    assert (root / "config" / "settings.yaml").is_file()
    assert (root / "config" / "tournaments.yaml").is_file()
    assert (root / "src").is_dir()
    assert (root / "app").is_dir()


def test_settings_load() -> None:
    settings = get_settings()
    assert settings["app"]["name"] == "CricketWorldCup Analytics"
    assert settings["app"]["version"] == "0.6.0"


def test_tournament_scope() -> None:
    tournaments = load_tournaments()
    assert len(tournaments) == 16
    ids = {t["tournament_id"] for t in tournaments}
    assert ids == EXPECTED_TOURNAMENT_IDS
    assert all(t.get("gender") == "Men" for t in tournaments)
    assert all(t.get("format") in {"ODI", "T20"} for t in tournaments)
    # No fabricated 2002 World Cup
    assert not any(t.get("year") == 2002 for t in tournaments)


def test_source_rules_present() -> None:
    rules = load_source_rules()
    assert rules["primary_source"]["name"] == "ESPNcricinfo"
    assert rules["robots"]["respect"] is True


def test_required_data_directories_exist() -> None:
    root = get_project_root()
    for relative in [
        "data/raw/tournaments",
        "data/raw/matches",
        "data/raw/scorecards",
        "data/raw/commentary",
        "data/processed/tournaments",
        "data/manifests",
        "data/warehouse/parquet",
        "logs",
    ]:
        assert (root / relative).is_dir(), relative


def test_manifest_headers_exist() -> None:
    root = get_project_root()
    for name in ["tournaments.csv", "match_urls.csv", "collection_status.csv"]:
        path = root / "data" / "manifests" / name
        assert path.is_file()
        header = path.read_text(encoding="utf-8").splitlines()[0]
        assert "tournament_id" in header or "entity_type" in header or "match_id" in header


def test_utc_now_iso_format() -> None:
    stamp = utc_now_iso()
    assert "T" in stamp
    assert stamp.endswith("+00:00") or stamp.endswith("Z") or "+" in stamp


def test_env_example_exists() -> None:
    root = get_project_root()
    assert (root / ".env.example").is_file()
    assert (root / "docker-compose.yml").is_file()
    assert (root / "requirements.txt").is_file()
