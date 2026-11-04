"""Stage 10: helper maths against known values, plus invariants of the real results."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
import pytest
from src.analytics import stats_tests as st

DB = Path(__file__).resolve().parents[1] / "data" / "warehouse" / "cricket_gold.duckdb"


def test_holm_matches_known_example() -> None:
    # Classic textbook example: sorted p = .01,.04,.03,.005 with m=4.
    adj = st.holm_adjust([0.01, 0.04, 0.03, 0.005])
    assert adj == pytest.approx([0.03, 0.06, 0.06, 0.02])
    assert all(a >= p for a, p in zip(adj, [0.01, 0.04, 0.03, 0.005], strict=True))
    assert max(st.holm_adjust([0.5, 0.9])) <= 1.0


def test_wilson_ci_properties() -> None:
    lo, hi = st.wilson_ci(50, 100)
    assert lo < 0.5 < hi and hi - lo == pytest.approx(0.192, abs=0.005)
    lo0, hi0 = st.wilson_ci(0, 10)
    assert lo0 == pytest.approx(0.0, abs=1e-9) and 0 < hi0 < 0.4
    assert np.isnan(st.wilson_ci(0, 0)[0])


def test_proportion_test_fair_and_biased() -> None:
    rate, p, lo, hi = st.proportion_test(50, 100)
    assert rate == 0.5 and p == pytest.approx(1.0)
    _, p_biased, *_ = st.proportion_test(80, 100)
    assert p_biased < 1e-6


def test_cramers_v_bounds() -> None:
    assert st.cramers_v(np.array([[50.0, 0.0], [0.0, 50.0]])) == pytest.approx(1.0)
    assert st.cramers_v(np.array([[25.0, 25.0], [25.0, 25.0]])) == pytest.approx(0.0)


def test_decided_excludes_ties_walkovers_and_no_result() -> None:
    m = pd.DataFrame(
        {
            "is_completed": [True, True, True, False],
            "is_walkover": [False, True, False, False],
            "is_tie": [False, False, True, False],
            "winner_id": ["a", "a", None, None],
            "batting_first_team_id": ["a", "a", "a", "a"],
            "toss_winner_id": ["a", "a", "a", "a"],
        }
    )
    assert len(st.decided(m)) == 1


@pytest.mark.skipif(not DB.exists(), reason="gold DuckDB not built")
def test_real_results_are_sane() -> None:
    results = {r.test_id: r for r in st.run_all()}
    assert len(results) >= 18
    for r in results.values():
        assert 0 <= r.p_value <= 1 and r.p_value <= r.p_adjusted <= 1, r.test_id
        assert r.n > 0
        if r.ci_low is not None:
            assert r.ci_low <= r.effect <= r.ci_high, r.test_id
    # Sanity checks that must hold for any correct implementation on real data:
    assert results["chase_vs_target_ODI"].effect < 1 and results["chase_vs_target_T20"].effect < 1
    assert results["scoring_trend_ODI"].effect > 0
    assert results["sixes_trend_T20"].effect > 1
