# ruff: noqa: E501
"""Machine learning for the Champions Trophy and the World Test Championship: honest match-winner models.

Everything shown is read from reports/model_evaluation (written by scripts/train_competition_models.py).
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
import plotly.graph_objects as go  # noqa: E402
import streamlit as st  # noqa: E402
from app.utils import database  # noqa: E402
from app.utils.theme import AMBER, BLUE, PINK, TEAL, cards  # noqa: E402
from app.utils.ui import setup  # noqa: E402

REPORTS = Path(__file__).resolve().parents[2] / "reports" / "model_evaluation"
LABELS = {
    "coin": "Coin flip",
    "elo_only": "Elo only (fixed formula)",
    "elo_logistic": "Elo gap, slope learned",
    "logistic": "Logistic regression (all features)",
    "random_forest": "Random forest (all features)",
}

if setup(
    "Machine Learning",
    "🤖",
    "Who wins a match? Honest models, tested only on matches played after the data they learned from.",
    ["match winner", "Elo ratings", "win probability", "calibration", "limits"],
):
    code = database.competition()
    is_test = code == "wtc"
    name = "World Test Championship" if is_test else "Champions Trophy"
    files = [REPORTS / f"{code}_{s}.csv" for s in ("winner_metrics", "winner_comparisons", "winner_predictions", "elo_ratings", "winner_calibration")]
    if not all(f.exists() for f in files):
        st.warning("The model reports for this competition have not been generated. Run scripts/build_competition_features.py and scripts/train_competition_models.py.")
        st.stop()
    metrics, comps, pred, elo, cal = (pd.read_csv(f) for f in files)
    info = json.loads((REPORTS / f"{code}_elo_model.json").read_text(encoding="utf-8"))
    n_test = int(metrics["n"].iloc[0])
    editions = sorted(pred["tournament_id"].unique())
    m = metrics.set_index("model")
    best = m.loc[["elo_only", "elo_logistic", "logistic", "random_forest"], "accuracy"].idxmax()
    any_clear = bool(comps[comps["versus"] == "elo_only"]["clearly_better"].any())

    cards(
        [
            ("Decided matches", str(info["decided_matches"]), "with a winner (no draws, ties or abandoned)"),
            ("Test matches scored", str(n_test), f"{len(editions)} editions, each after earlier ones"),
            ("Coin flip", f"{100 * m.loc['coin', 'accuracy']:.0f}%", "the baseline to beat"),
            ("Best model", f"{100 * m.loc[best, 'accuracy']:.0f}%", LABELS[best]),
        ]
    )
    tabs = st.tabs(["Match winner", "Elo ratings", "Win probability", "Calibration", "Limits"])

    with tabs[0]:
        elo_beats_coin = m.loc["elo_only", "accuracy_low"] > 0.5
        if elo_beats_coin:
            verdict = (
                f"**Team strength (Elo) predicts the winner better than a coin flip.** Elo alone gets {100 * m.loc['elo_only', 'accuracy']:.0f}% right "
                f"(95% interval {100 * m.loc['elo_only', 'accuracy_low']:.0f}-{100 * m.loc['elo_only', 'accuracy_high']:.0f}%), and the interval stays above 50%. "
                + ("No richer model is clearly better than Elo." if not any_clear else "At least one richer model is clearly better than Elo.")
            )
            st.success(verdict)
        else:
            st.warning(
                f"**No model clearly beats a coin flip here.** Elo alone gets {100 * m.loc['elo_only', 'accuracy']:.0f}% right "
                f"(95% interval {100 * m.loc['elo_only', 'accuracy_low']:.0f}-{100 * m.loc['elo_only', 'accuracy_high']:.0f}%), which includes 50%. "
                f"With {n_test} test matches and very little history per team, this is the honest result: the data cannot support a predictive claim."
            )
        show = metrics.assign(model=metrics["model"].map(LABELS))
        show["accuracy"] = (100 * show["accuracy"]).round(1)
        show["95% interval"] = [f"{100 * a:.0f}-{100 * b:.0f}%" for a, b in zip(show["accuracy_low"], show["accuracy_high"], strict=True)]
        st.dataframe(
            show[["model", "n", "accuracy", "95% interval", "log_loss", "brier", "auc"]].rename(columns={"accuracy": "accuracy %"}).round(3),
            hide_index=True,
            width="stretch",
        )
        fig = go.Figure(
            go.Bar(
                x=[LABELS[x] for x in metrics["model"]],
                y=100 * metrics["accuracy"],
                marker_color=[AMBER if x == "coin" else TEAL if x.startswith("elo") else BLUE for x in metrics["model"]],
                error_y=dict(type="data", symmetric=False, array=100 * (metrics["accuracy_high"] - metrics["accuracy"]), arrayminus=100 * (metrics["accuracy"] - metrics["accuracy_low"])),
                hovertemplate="%{x}: %{y:.1f}%<extra></extra>",
            )
        )
        fig.add_hline(y=50, line_dash="dash", line_color="rgba(255,255,255,.5)")
        fig.update_layout(title="Accuracy on matches played after the training data (bars = 95% interval)", yaxis_title="Accuracy %", yaxis_range=[0, 100], height=420)
        st.plotly_chart(fig, width="stretch")
        st.markdown("**Is a model better than Elo alone? (paired bootstrap on the same matches)**")
        c = comps[comps["versus"] == "elo_only"].assign(model=lambda d: d["model"].map(LABELS))
        c["difference (points)"] = (100 * c["accuracy_difference"]).round(1)
        c["95% interval"] = [f"{100 * a:.0f} to {100 * b:.0f}" for a, b in zip(c["ci_low"], c["ci_high"], strict=True)]
        c["clearly better"] = c["clearly_better"].map({True: "yes", False: "no"})
        st.dataframe(c[["model", "difference (points)", "95% interval", "clearly better"]], hide_index=True, width="stretch")
        st.caption(
            "How it was tested: editions are scored in time order, and each is predicted by a model fitted only on earlier editions. "
            "Hyperparameters are fixed in advance (nothing tuned on the test matches). Features use only matches played before each match."
        )

    with tabs[1]:
        fmt = "Test" if is_test else "ODI"
        e = elo[elo["format"] == fmt].sort_values("elo", ascending=False)
        fig = go.Figure(go.Bar(x=e["elo"] - 1500, y=e["team"], orientation="h", marker_color=TEAL, base=1500, hovertemplate="%{y}: %{customdata:.0f}<extra></extra>", customdata=e["elo"]))
        fig.update_layout(title=f"{name}: Elo rating after the last match (everyone starts at 1500)", height=max(320, 40 * len(e) + 120), yaxis=dict(autorange="reversed"), xaxis_title="Elo")
        st.plotly_chart(fig, width="stretch")
        st.dataframe(e.reset_index(drop=True), hide_index=True, width="stretch")
        st.caption(
            "Elo moves points between teams after every decided match (K = 30)."
            + (" A draw counts as half a win for each side, so a stronger team loses a few points by drawing." if is_test else " Abandoned and no-result matches do not move ratings.")
        )

    with tabs[2]:
        teams = e["team"].tolist() if len(e) else []
        a, b = st.columns(2)
        with a:
            ta = st.selectbox("Team A", teams, index=0, key="ml_team_a")
        with b:
            tb = st.selectbox("Team B", teams, index=min(1, len(teams) - 1), key="ml_team_b")
        ra, rb = float(e.loc[e["team"] == ta, "elo"].iloc[0]), float(e.loc[e["team"] == tb, "elo"].iloc[0])
        p = 1.0 / (1.0 + np.exp(-info["slope_per_elo_point"] * (ra - rb)))
        if ta == tb:
            st.info("Pick two different teams.")
        else:
            cards(
                [
                    (f"{ta}", f"{100 * p:.0f}%", f"Elo {ra:.0f}"),
                    (f"{tb}", f"{100 * (1 - p):.0f}%", f"Elo {rb:.0f}"),
                    ("Elo gap", f"{ra - rb:+.0f}", "points"),
                ]
            )
            st.caption(
                "Chance that the first team wins **if the match is decided**, from the Elo gap alone, with the slope learned on every decided match. "
                + ("In Tests a draw is also possible and is not predicted here. " if is_test else "")
                + "Home advantage, pitch and the team selected are not modelled. Treat this as a rough guide, not a forecast."
            )

    with tabs[3]:
        cal_models = [x for x in ("elo_only", "elo_logistic", "logistic") if x in set(cal["model"])]
        fig = go.Figure()
        fig.add_scatter(x=[0, 1], y=[0, 1], mode="lines", line=dict(dash="dash", color="rgba(255,255,255,.5)"), name="perfect")
        for model, col in zip(cal_models, (TEAL, BLUE, PINK), strict=False):
            g = cal[cal["model"] == model]
            fig.add_scatter(x=g["mean_predicted"], y=g["actual_rate"], mode="lines+markers", name=LABELS[model], line=dict(color=col), customdata=g["n"], hovertemplate="predicted %{x:.2f}, actual %{y:.2f} (%{customdata} matches)<extra></extra>")
        fig.update_layout(title="Calibration: predicted win chance against how often it happened", xaxis_title="Predicted win probability", yaxis_title="Actual win rate", height=420)
        st.plotly_chart(fig, width="stretch")
        st.caption("Points near the dashed line mean the stated probabilities were honest. Each point is a group of matches, so with this few matches the curve is noisy.")

    with tabs[4]:
        st.markdown(
            f"""
- **Small data.** Only {info['decided_matches']} matches have a winner and {n_test} could be used as a fair test. Differences of a few points are noise (see the intervals).
- **What is predicted.** A winner among decided matches. {"Draws (29 Tests) are not predicted and do not count as results to learn from." if is_test else "Ties, abandoned and no-result matches are not predicted."}
- **What is not modelled.** Home advantage, pitch and weather, toss, the playing XI, injuries and the points race are not in the features.
- **Why Elo.** It is the simplest honest summary of team strength: it only uses who beat whom, and it beat or matched every richer model here.
- **Not the World Cup models.** These are separate models trained on this competition only; the World Cup models are not used for {name}.
- **Reproduce.** `python scripts/build_competition_features.py` then `python scripts/train_competition_models.py`.
"""
        )
