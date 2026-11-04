# ruff: noqa: E501
"""Dashboard: every page renders, every spec'd view exists, numbers are right, and the failure modes
we have actually hit (bare conditional expressions printing Streamlit internals) cannot come back."""

from __future__ import annotations

import ast
from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

ROOT = Path(__file__).resolve().parents[1]
DB = ROOT / "data" / "warehouse" / "cricket_gold.duckdb"
APP = ROOT / "app"
PAGES = sorted((APP / "pages").glob("[0-9]*.py"))
ALL_SOURCES = [APP / "dashboard.py", *PAGES, *sorted((APP / "utils").glob("*.py"))]

pytestmark = pytest.mark.skipif(not DB.exists(), reason="gold DuckDB not built")


def page(name: str, timeout: int = 240) -> AppTest:
    return AppTest.from_file(str(APP / "pages" / name), default_timeout=timeout)


def visible_text(at: AppTest) -> list[str]:
    return [
        str(x.value)
        for group in (at.markdown, at.caption, at.code, at.text, at.warning, at.info, at.success)
        for x in group
    ]


# ----------------------------------------------------------------------------- source-level guards
@pytest.mark.parametrize("path", ALL_SOURCES, ids=lambda p: p.name)
def test_no_bare_expressions_that_streamlit_magic_would_print(path: Path) -> None:
    """`st.dataframe(x) if cond else st.caption(y)` as a statement makes Streamlit's 'magic' print the returned
    DeltaGenerator object (this is the bug that dumped API docs onto the pages). Only calls, strings and
    awaits may stand alone as statements."""
    tree = ast.parse(path.read_text(encoding="utf-8-sig"))
    bad = [
        (n.lineno, type(n.value).__name__)
        for n in ast.walk(tree)
        if isinstance(n, ast.Expr)
        and not isinstance(n.value, (ast.Call, ast.Constant, ast.Await, ast.JoinedStr))
    ]
    assert not bad, f"{path.name}: bare expression statements {bad}"


def test_every_file_uses_the_non_deprecated_width_argument() -> None:
    offenders = [
        p.name for p in ALL_SOURCES if "use_container_width" in p.read_text(encoding="utf-8-sig")
    ]
    assert not offenders, offenders


# ----------------------------------------------------------------------------- structure
def test_page_set_matches_the_spec_plus_squads() -> None:
    assert [p.stem for p in PAGES] == [
        "01_Tournament_Explorer",
        "02_Player_Analytics",
        "03_Team_Analytics",
        "04_Squads",
        "05_Match_Analytics",
        "06_Ball_by_Ball_Analytics",
        "07_Statistical_Research",
        "08_Machine_Learning",
        "09_Data_Engineering",
        "10_Historical_Records",
    ]


def test_theme_files_exist() -> None:
    cfg = (ROOT / ".streamlit" / "config.toml").read_text(encoding="utf-8")
    assert 'base = "dark"' in cfg
    from app.utils import theme

    assert "gradient" in theme.CSS and "hero" in theme.CSS
    assert theme.plotly_template().layout.colorway


def test_home_shows_every_required_kpi() -> None:
    at = AppTest.from_file(str(APP / "dashboard.py"), default_timeout=180).run()
    assert not at.exception, at.exception
    labels = {m.label: m.value for m in at.metric}
    for k in (
        "Tournaments",
        "Matches",
        "Teams",
        "Players",
        "Total runs",
        "Total wickets",
        "Data quality score",
        "Ball-by-ball coverage",
    ):
        assert k in labels, k
    assert labels["Matches"] == "677" and labels["Tournaments"] == "16" and labels["Teams"] == "26"
    assert (
        int(labels["Total runs"].replace(",", "")) > 100_000
        and int(labels["Total wickets"].replace(",", "")) > 5_000
    )
    assert labels["Ball-by-ball coverage"].endswith("%") and "/ 100" in labels["Data quality score"]


@pytest.mark.parametrize("path", [APP / "dashboard.py", *PAGES], ids=lambda p: p.stem)
def test_page_renders_with_hero_and_without_leaks(path: Path) -> None:
    at = AppTest.from_file(str(path), default_timeout=240).run()
    assert not at.exception, f"{path.name}: {at.exception}"
    text = visible_text(at)
    assert any('class="hero"' in t for t in text), "hero banner missing"
    leaks = [t[:80] for t in text if "DeltaGenerator" in t or "Creator of Delta" in t]
    assert not leaks, f"{path.name} prints Streamlit internals: {leaks}"


@pytest.mark.parametrize(
    "name,expected",
    [
        (
            "01_Tournament_Explorer.py",
            ["Overview", "Standings", "Results", "Awards", "Statistics", "Batting and bowling"],
        ),
        (
            "02_Player_Analytics.py",
            [
                "Profile",
                "Batting detail",
                "Bowling detail",
                "Comparison",
                "Consistency",
                "Clustering",
            ],
        ),
        (
            "03_Team_Analytics.py",
            [
                "World Cup history",
                "Strength and Elo",
                "Batting and bowling",
                "Comparison",
                "Head-to-head",
                "Players",
            ],
        ),
        ("04_Squads.py", ["Squad", "Composition", "Compare squads", "Continuity", "Player lookup"]),
        (
            "05_Match_Analytics.py",
            [
                "Match explorer",
                "Toss",
                "Batting first vs chasing",
                "Winning margins",
                "ODI vs T20",
                "Venues",
                "Historical trends",
            ],
        ),
        (
            "06_Ball_by_Ball_Analytics.py",
            [
                "Run and wicket progression",
                "Over by over",
                "Scoring phases",
                "Partnerships and batters",
                "Bowlers",
                "Delivery patterns",
                "First-innings projection",
                "Deliveries",
            ],
        ),
        (
            "07_Statistical_Research.py",
            [
                "Research questions",
                "Tests and intervals",
                "Visualisations",
                "Regression",
                "Written conclusions",
            ],
        ),
        (
            "08_Machine_Learning.py",
            [
                "Match winner",
                "Live innings projection",
                "Pre-match score",
                "Player models",
                "Importance and SHAP",
                "Model comparison",
            ],
        ),
        (
            "09_Data_Engineering.py",
            [
                "Pipeline",
                "Freshness and inventory",
                "Data quality",
                "Missing data",
                "Validation failures",
                "Lineage",
                "Coverage",
            ],
        ),
        ("10_Historical_Records.py", ["Hall of fame", "Query explorer"]),
    ],
)
def test_each_spec_view_exists(name: str, expected: list[str]) -> None:
    at = page(name).run()
    assert not at.exception, at.exception
    assert [t.label for t in at.tabs] == expected


@pytest.mark.parametrize(
    "name,minimum",
    [
        ("01_Tournament_Explorer.py", 15),
        ("02_Player_Analytics.py", 20),
        ("03_Team_Analytics.py", 14),
        ("04_Squads.py", 14),
        ("05_Match_Analytics.py", 20),
        ("06_Ball_by_Ball_Analytics.py", 18),
        ("07_Statistical_Research.py", 10),
        ("08_Machine_Learning.py", 16),
        ("09_Data_Engineering.py", 12),
        ("10_Historical_Records.py", 4),
    ],
)
def test_pages_are_full_of_charts(name: str, minimum: int) -> None:
    at = page(name).run()
    assert len(at.get("plotly_chart")) >= minimum, (name, len(at.get("plotly_chart")))


def test_dashboard_has_a_large_visual_inventory() -> None:
    total = 0
    for p in [APP / "dashboard.py", *PAGES]:
        total += len(AppTest.from_file(str(p), default_timeout=240).run().get("plotly_chart"))
    assert total >= 160


# ----------------------------------------------------------------------------- behaviour
def test_squads_page_shows_a_real_squad() -> None:
    at = page("04_Squads.py").run()
    assert not at.exception, at.exception
    text = " ".join(visible_text(at))
    assert "Squad size" in text and "Average age" in text and "Captain" in text
    assert len(at.dataframe) >= 1 and len(at.get("plotly_chart")) >= 10


def test_squads_page_can_switch_team_and_format() -> None:
    at = page("04_Squads.py").run()
    at.sidebar.radio[0].set_value("T20").run()
    assert not at.exception, at.exception
    team = at.sidebar.selectbox[0]
    other = [o for o in team.options if o != team.value][0]
    team.select(other).run()
    assert not at.exception, at.exception


def test_player_search_and_comparison() -> None:
    at = page("02_Player_Analytics.py").run()
    at.sidebar.text_input[0].set_value("Guptill").run()
    assert not at.exception and any("Guptill" in o for o in at.sidebar.selectbox[0].options)
    at.sidebar.text_input[1].set_value("Williamson").run()
    assert not at.exception
    assert any("Williamson" in o for o in at.sidebar.selectbox[1].options)


def test_player_profile_has_role_and_radar() -> None:
    at = page("02_Player_Analytics.py").run()
    text = " ".join(visible_text(at))
    assert "Virat Kohli" in text and "Batting style" in text and "Role" in text


def test_player_clusters_and_consistency_render() -> None:
    at = page("02_Player_Analytics.py").run()
    assert not at.exception
    text = " ".join(visible_text(at))
    assert "Minimum samples" in text and "continuum" in text


def test_team_page_elo_and_head_to_head_render() -> None:
    at = page("03_Team_Analytics.py").run()
    assert not at.exception, at.exception
    at.sidebar.selectbox[0].select("Pakistan").run()
    assert not at.exception, at.exception


def test_match_explorer_shows_scorecard() -> None:
    at = page("05_Match_Analytics.py").run()
    assert not at.exception, at.exception
    assert len(at.dataframe) >= 4


def test_synthetic_conditions_are_labelled_in_the_ui() -> None:
    at = page("05_Match_Analytics.py").run()
    assert any("SYNTHETIC" in w.value for w in at.warning) or any(
        "SYNTHETIC" in e.label for e in at.expander
    )


def test_ball_by_ball_second_innings_shows_the_chase() -> None:
    at = page("06_Ball_by_Ball_Analytics.py").run()
    inn = at.sidebar.selectbox[1]
    if 2 in list(inn.options) or "2" in [str(o) for o in inn.options]:
        inn.select(2 if 2 in list(inn.options) else "2").run()
    assert not at.exception, at.exception


def test_win_predictor_probabilities_are_complementary_and_swap_exactly() -> None:
    at = page("08_Machine_Learning.py").run()
    assert not at.exception, at.exception
    vals = [float(m.value.rstrip("%")) for m in at.metric[:2]]
    assert abs(sum(vals) - 100) < 0.2
    sel = [s for s in at.selectbox if s.label in ("Team A", "Team B")]
    a, b = sel[0].value, sel[1].value
    sel[0].select(b)
    sel[1].select(a)
    at.run()
    swapped = [float(m.value.rstrip("%")) for m in at.metric[:2]]
    assert abs(swapped[0] - vals[1]) < 0.15 and abs(swapped[1] - vals[0]) < 0.15


def test_the_curve_shown_is_the_deployed_models_own_curve() -> None:
    """The headline probability must equal what the deployed model's curve gives at the pair's Elo gap
    (a past bug plotted the textbook Elo formula under a probability produced by a different curve)."""
    import numpy as np
    import pandas as pd
    from src.features.match_features import load_matches, load_performances
    from src.ml import serving

    at = page("08_Machine_Learning.py").run()
    shown = float(at.metric[0].value.rstrip("%")) / 100
    teams = {s.label: s.value for s in at.selectbox if s.label in ("Team A", "Team B")}
    row = serving.hypothetical_features(
        load_matches(), load_performances(), "ODI", teams["Team A"], teams["Team B"]
    )
    g = float(row["elo_diff"])
    pack = serving.load_model("winner_elo_logistic")
    pa = pack["model"].predict_proba(pd.DataFrame({"elo_diff": [g]}))[0, 1]
    pb = pack["model"].predict_proba(pd.DataFrame({"elo_diff": [-g]}))[0, 1]
    assert abs(0.5 * (pa + 1 - pb) - shown) < 0.002 and np.isfinite(shown)


def test_logistic_model_choice_shows_a_shap_explanation() -> None:
    at = page("08_Machine_Learning.py").run()
    at.selectbox[0].select("Logistic regression (13 features)").run()
    assert not at.exception, at.exception
    assert any("Prediction explanation" in m.value for m in at.markdown)


def test_model_page_text_matches_the_data() -> None:
    at = page("08_Machine_Learning.py").run()
    assert "lowest log-loss" in " ".join(m.value for m in at.markdown)


def test_data_engineering_reports_the_pipeline_run() -> None:
    at = page("09_Data_Engineering.py").run()
    assert not at.exception
    assert any(m.label == "Result" for m in at.metric)


def test_stat_research_conclusions_are_generated() -> None:
    at = page("07_Statistical_Research.py").run()
    text = " ".join(m.value for m in at.markdown)
    assert "Holm-adjusted p" in text and "toss_win_rate_ODI" in text


def test_records_hall_of_fame_has_known_records() -> None:
    at = page("10_Historical_Records.py").run()
    text = " ".join(visible_text(at))
    assert "237" in text and "Guptill" in text and "428" in text


# ----------------------------------------------------------------------------- data behind the visuals
def test_squad_data_is_complete_and_sane() -> None:
    from app.utils import viz_data as V

    sq = V.squads_all()
    assert len(sq) == 3624 and sq["team_id"].nunique() == 26 and sq["tournament_id"].nunique() == 16
    sizes = sq.groupby(["tournament_id", "team_id"]).size()
    assert len(sizes) == 230 and sizes.min() >= 14 and sizes.max() <= 20
    assert sq.groupby(["tournament_id", "team_id"])["is_captain"].sum().min() >= 1
    assert sq["age_at_tournament"].dropna().between(15, 50).all()
    usa = sq[
        (sq["tournament_id"] == "T20_M_2026") & (sq["team_name"] == "United States of America")
    ]
    assert len(usa) == 15 and usa["source"].astype(str).str.contains("manual").any()


def test_queries_return_known_facts() -> None:
    from app.utils import queries as Q

    t = Q.tournaments()
    assert len(t) == 16 and set(t["format"]) == {"ODI", "T20"}
    tid = t[(t["format"] == "ODI") & (t["year"] == 2023)]["tournament_id"].iloc[0]
    assert Q.top_batters(tid, 1)["player"].iloc[0] == "Virat Kohli"
    assert int(Q.top_batters(tid, 1)["runs"].iloc[0]) == 765
    assert len(Q.matches_of(tid)) == 48 and not Q.standings(tid).empty
    assert len(Q.parse_library()) >= 30 and Q.coverage()["played_matches"].sum() == 652
    assert (
        Q.team_record(Q.teams().set_index("team_name").loc["India", "team_id"])["tournament"]
        .str.match(r"^(ODI|T20) \d{4}$")
        .all()
    )


def test_long_chart_titles_are_wrapped_not_truncated() -> None:
    import plotly.graph_objects as go
    from app.utils.theme import wrap_title

    fig = go.Figure()
    fig.update_layout(
        title="First vs second innings score (above the line = chasing side scored more)"
    )
    wrap_title(fig)
    assert "<br>" in fig.layout.title.text
    short = go.Figure().update_layout(title="Short title")
    wrap_title(short)
    assert "<br>" not in short.layout.title.text
