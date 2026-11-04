# ruff: noqa: E501
"""The six reports named in the brief: ten sections in order, figures exist, claims come from the data."""

from __future__ import annotations

import re
from pathlib import Path

import pandas as pd
import pytest
from src.reporting import spec_reports as sr

ROOT = Path(__file__).resolve().parents[1]
REPORTS = ROOT / "reports"
needs = pytest.mark.skipif(not (REPORTS / "cricket_insights_report.md").exists(), reason="reports not built")


def test_assemble_enforces_the_ten_sections() -> None:
    body = {name: "x" for name in sr.SECTIONS}
    text = sr.assemble("T", body)
    assert [m for m in re.findall(r"^## \d+\. (.+)$", text, re.M)] == sr.SECTIONS
    with pytest.raises(AssertionError):
        sr.assemble("T", {k: "x" for k in sr.SECTIONS[:-1]})
    with pytest.raises(AssertionError):
        sr.assemble("T", dict(reversed(list(body.items()))))


def test_section_names_match_the_brief() -> None:
    assert sr.SECTIONS == ["Research objective", "Dataset used", "Methodology", "Data limitations", "Analysis", "Results", "Visualizations", "Interpretation", "Conclusion", "Reproducibility instructions"]
    assert sr.REPORT_FILES == ["data_quality_report.md", "data_engineering_report.md", "exploratory_analysis_report.md", "statistical_analysis_report.md", "machine_learning_report.md", "cricket_insights_report.md"]


@needs
@pytest.mark.parametrize("name", sr.REPORT_FILES)
def test_report_has_all_sections_with_content(name: str) -> None:
    text = (REPORTS / name).read_text(encoding="utf-8")
    heads = re.findall(r"^## \d+\. (.+)$", text, re.M)
    assert heads == sr.SECTIONS
    chunks = re.split(r"^## \d+\. .+$", text, flags=re.M)[1:]
    assert all(len(c.strip()) > 20 for c in chunks), "a section is empty"
    assert "input missing" not in text and "_missing_" not in text and "(no data)" not in text


@needs
@pytest.mark.parametrize("name", sr.REPORT_FILES)
def test_report_images_exist(name: str) -> None:
    text = (REPORTS / name).read_text(encoding="utf-8")
    for rel in re.findall(r"!\[[^\]]*\]\(([^)]+)\)", text):
        assert (REPORTS / rel).exists(), f"{name}: missing image {rel}"


@needs
def test_no_unexplained_quality_failures() -> None:
    text = (REPORTS / "data_quality_report.md").read_text(encoding="utf-8")
    assert "no documented explanation" not in text


def test_explain_failures_flags_unknown_rules() -> None:
    f = pd.DataFrame([{"rule_id": "gold.brand_new_rule", "severity": "critical", "total": 10, "failed": 2, "failed_pct": 20.0}])
    assert "no documented explanation" in sr.explain_failures(f)
    assert sr.explain_failures(pd.DataFrame()) == "No rule fails."


@needs
def test_insight_numbers_match_the_source_tests() -> None:
    t = pd.read_csv(REPORTS / "statistical_tests.csv").set_index("test_id")
    text = (REPORTS / "cricket_insights_report.md").read_text(encoding="utf-8")
    assert f"{100 * t.loc['toss_win_rate_ODI', 'effect']:.1f}%" in text
    assert f"{t.loc['chase_vs_target_T20', 'effect']:.2f}" in text
    # every insight names its source
    insights = re.findall(r"^\d+\. .+$", text, re.M)
    assert len(insights) >= 10 and text.count("_Source:") == len(insights)


@needs
def test_ml_report_states_the_late_innings_limit_from_data() -> None:
    text = (REPORTS / "machine_learning_report.md").read_text(encoding="utf-8")
    m = pd.read_csv(REPORTS / "model_evaluation" / "innings_projection_metrics.csv")
    t20 = m[(m.format == "T20") & (m.scope == "over 18")].set_index("model")["mae"]
    assert f"{t20['linear_regression']:.1f} vs {t20['baseline_run_rate']:.1f}" in text


@needs
def test_original_stage3_report_is_kept() -> None:
    assert (REPORTS / "data_quality" / "operational_data_quality_report.md").exists()
