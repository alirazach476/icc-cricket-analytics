# ruff: noqa: E501
"""Machine learning: model selection, prediction interfaces, performance, importance and explanations."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
import plotly.express as px  # noqa: E402
import plotly.graph_objects as go  # noqa: E402
import streamlit as st  # noqa: E402
from app.utils import analytics as A  # noqa: E402
from app.utils import charts as C  # noqa: E402
from app.utils import queries as Q  # noqa: E402
from app.utils.theme import AMBER, BLUE, PINK, TEAL, cards, flag  # noqa: E402
from app.utils.ui import setup  # noqa: E402
from src.features.match_features import FEATURES_WINNER, load_matches, load_performances  # noqa: E402
from src.ml import explain as ex  # noqa: E402
from src.ml import serving  # noqa: E402


@st.cache_data(show_spinner="Loading match history...")
def history():
    return load_matches(), load_performances()


def table(rel: str) -> None:
    d = A.report_csv(rel)
    if d is None:
        st.info(f"Missing reports/{rel}; run the pipeline.")
    else:
        st.dataframe(d.round(3), hide_index=True, width="stretch")


def comparison_sentence() -> str:
    c = A.report_csv("model_evaluation/winner_comparisons.csv")
    m = A.report_csv("model_comparison/winner_metrics.csv")
    if c is None or m is None:
        return ""
    sig = c[c["beats_elo_significantly"]]["model"].tolist()
    a = m[m["scope"] == "all"].set_index("model")
    best_ll = a.drop(index=["coin"])["log_loss"].idxmin()
    txt = f"Out-of-time, the lowest log-loss is **{best_ll}** ({a.loc[best_ll, 'log_loss']:.3f}) versus Elo-only ({a.loc['elo_only', 'log_loss']:.3f}). "
    if sig:
        txt += f"On accuracy, {', '.join(sig)} beat(s) Elo-only with an interval above zero, but {len(c)} models were compared, so a single such result is not robust, and log-loss does not improve."
    else:
        txt += "No model beats Elo-only on accuracy with an interval above zero."
    return txt


if setup(
    "Machine Learning",
    "🧠",
    "Match-winner and score models evaluated out of time, with prediction interfaces, calibration, importance and per-prediction explanations.",
    ["out-of-time validation", "calibration", "SHAP", "live projection"],
):
    wm = A.report_csv("model_comparison/winner_metrics.csv")
    if wm is not None:
        a_ = wm[wm["scope"] == "all"].set_index("model")
        cards(
            [
                (
                    "Elo-only accuracy",
                    f"{100 * a_.loc['elo_only', 'accuracy']:.1f}%",
                    "out of time",
                ),
                ("Coin flip", f"{100 * a_.loc['coin', 'accuracy']:.1f}%", "baseline"),
                (
                    "Best log-loss",
                    f"{a_.drop(index=['coin'])['log_loss'].min():.3f}",
                    a_.drop(index=["coin"])["log_loss"].idxmin(),
                ),
                ("Test matches", f"{int(a_.loc['elo_only', 'n'])}", "decided, held-out"),
            ],
            [TEAL, "#8FA0C0", BLUE, AMBER],
        )
    tabs = st.tabs(
        [
            "Match winner",
            "Live innings projection",
            "Pre-match score",
            "Player models",
            "Importance and SHAP",
            "Model comparison",
        ]
    )

    with tabs[0]:
        st.markdown(comparison_sentence())
        sel = st.selectbox(
            "Model for the interface below",
            ["Elo only (simplest, recommended)", "Logistic regression (13 features)"],
        )
        model_name = "winner_elo_logistic" if sel.startswith("Elo") else "winner_logistic"
        matches, perf = history()
        teams = Q.teams()
        names = dict(zip(teams["team_id"], teams["team_name"], strict=True))
        fmt = st.radio("Format", ["ODI", "T20"], horizontal=True)
        active = sorted(
            set(matches.loc[matches["format"] == fmt, "team1_id"])
            | set(matches.loc[matches["format"] == fmt, "team2_id"]),
            key=lambda t: names.get(t, t),
        )
        c = st.columns(3)
        ta = c[0].selectbox(
            "Team A",
            active,
            format_func=lambda t: f"{flag(names.get(t, t))} {names.get(t, t)}",
            index=0,
        )
        tb = c[1].selectbox(
            "Team B",
            active,
            format_func=lambda t: f"{flag(names.get(t, t))} {names.get(t, t)}",
            index=min(1, len(active) - 1),
        )
        ko = c[2].checkbox("Knockout match")
        if ta == tb:
            st.warning("Pick two different teams.")
        else:
            p = serving.win_probability(matches, perf, fmt, ta, tb, model_name, knockout=ko)
            m = st.columns(2)
            m[0].metric(names[ta], f"{100 * p:.1f}%")
            m[1].metric(names[tb], f"{100 * (1 - p):.1f}%")
            fig = go.Figure(
                go.Bar(
                    x=[100 * p, 100 * (1 - p)],
                    y=[""] * 2,
                    orientation="h",
                    marker=dict(color=[BLUE, AMBER]),
                    text=[f"{names[ta]} {100 * p:.0f}%", f"{names[tb]} {100 * (1 - p):.0f}%"],
                    textposition="inside",
                )
            )
            fig.update_layout(
                barmode="stack",
                height=110,
                showlegend=False,
                margin=dict(l=0, r=0, t=0, b=0),
                xaxis=dict(visible=False),
                yaxis=dict(visible=False),
            )
            st.plotly_chart(fig, width="stretch")
            row = serving.hypothetical_features(matches, perf, fmt, ta, tb, knockout=ko)
            st.markdown("**Prediction explanation**")
            if model_name == "winner_logistic":
                pack = serving.load_model("winner_logistic")
                labelled = A.feature_parquet("match_features.parquet")
                labelled = labelled[labelled["y_a_wins"].notna()]
                X = pd.DataFrame([row[FEATURES_WINNER].astype(float)])
                vals, base = ex.shap_values(pack["model"], X, labelled)
                sh = pd.DataFrame(
                    {
                        "feature": FEATURES_WINNER,
                        "value": X.iloc[0].to_numpy(),
                        "contribution (log-odds)": vals[0],
                    }
                )
                sh = sh.reindex(
                    sh["contribution (log-odds)"].abs().sort_values(ascending=False).index
                )
                top = sh.head(8)
                fig = C.waterfall(
                    [f"{f} = {v:.2f}" for f, v in zip(top["feature"], top["value"], strict=True)],
                    top["contribution (log-odds)"],
                    f"What pushes the model towards {names[ta]} (up) or {names[tb]} (down)",
                    380,
                )
                st.plotly_chart(fig, width="stretch")
                st.dataframe(sh.round(3), hide_index=True, width="stretch")
                st.caption(
                    "SHAP contributions of the un-symmetrised model in the A-vs-B orientation; the headline probability averages both orientations."
                )
            else:
                g = serving.hypothetical_features(matches, perf, fmt, ta, tb)
                pack = serving.load_model("winner_elo_logistic")
                grid = np.linspace(-500, 500, 101)
                pa = pack["model"].predict_proba(pd.DataFrame({"elo_diff": grid}))[:, 1]
                pb = pack["model"].predict_proba(pd.DataFrame({"elo_diff": -grid}))[:, 1]
                curve = pd.DataFrame(
                    {
                        "gap": grid,
                        "model": 0.5 * (pa + 1 - pb),
                        "textbook Elo": 1 / (1 + 10 ** (-grid / 400)),
                    }
                )
                long = curve.melt(id_vars="gap", var_name="curve", value_name="win probability")
                fig = px.line(
                    long,
                    x="gap",
                    y="win probability",
                    color="curve",
                    title=f"The deployed model's curve: {names[ta]} {g['elo_a']:.0f} vs {names[tb]} {g['elo_b']:.0f} (gap {g['elo_diff']:+.0f})",
                    color_discrete_map={"model": TEAL, "textbook Elo": "#8FA0C0"},
                )
                fig.update_traces(selector=dict(name="textbook Elo"), line=dict(dash="dot"))
                fig.add_vline(x=float(g["elo_diff"]), line_dash="dash", line_color=AMBER)
                fig.update_layout(height=340, yaxis_tickformat=".0%")
                st.plotly_chart(fig, width="stretch")
                st.caption(
                    "The model's curve is steeper than the textbook Elo formula because the fitted data say rating gaps matter more here (see Statistical Research)."
                )
        st.subheader("Performance (out-of-time folds, decided matches)")
        wa = wm[wm["scope"] == "all"] if wm is not None else None
        pred = A.report_csv("model_evaluation/winner_predictions.csv")
        if wa is not None:
            a, b = st.columns(2)
            with a:
                long = wa.melt(
                    id_vars="model",
                    value_vars=["accuracy", "precision", "recall", "f1"],
                    var_name="metric",
                    value_name="value",
                )
                st.plotly_chart(
                    px.bar(
                        long,
                        x="model",
                        y="value",
                        color="metric",
                        barmode="group",
                        title="Accuracy, precision, recall, F1",
                    ).update_layout(height=380, xaxis_tickangle=-30),
                    width="stretch",
                )
            with b:
                lb = wa.melt(
                    id_vars="model",
                    value_vars=["log_loss", "brier"],
                    var_name="metric",
                    value_name="value",
                )
                st.plotly_chart(
                    px.bar(
                        lb,
                        x="model",
                        y="value",
                        color="metric",
                        barmode="group",
                        title="Log loss and Brier score (lower is better)",
                        color_discrete_sequence=[PINK, TEAL],
                    ).update_layout(height=380, xaxis_tickangle=-30),
                    width="stretch",
                )
        if pred is not None:
            models_ = [
                m_ for m_ in ("elo_only", "logistic", "random_forest", "xgboost") if m_ in pred
            ]
            a, b = st.columns(2)
            with a:
                st.plotly_chart(C.roc_curves(pred, models_), width="stretch")
            with b:
                pick = st.selectbox("Confusion matrix for", models_, index=min(1, len(models_) - 1))
                g = pred[pred[pick].notna()]
                st.plotly_chart(
                    C.confusion(g["y"], g[pick], f"{pick}: predicted vs actual", 330),
                    width="stretch",
                )
            cal = A.report_csv("model_evaluation/winner_calibration_curves.csv")
            if cal is not None:
                fig = go.Figure(
                    go.Scatter(
                        x=[0, 1],
                        y=[0, 1],
                        mode="lines",
                        line=dict(dash="dash", color="rgba(255,255,255,.4)"),
                        name="perfect",
                    )
                )
                for m_, g in cal.groupby("model"):
                    fig.add_trace(
                        go.Scatter(
                            x=g["mean_predicted"],
                            y=g["observed_rate"],
                            mode="lines+markers",
                            name=m_,
                            marker=dict(size=g["n"] / 6),
                        )
                    )
                fig.update_layout(
                    title="Calibration: predicted probability vs what happened",
                    height=400,
                    xaxis_title="predicted",
                    yaxis_title="observed",
                )
                st.plotly_chart(fig, width="stretch")
            byt = (
                pred.assign(correct=((pred["elo_only"] > 0.5) == (pred["y"] == 1)))
                .groupby("tournament_id", as_index=False)
                .agg(accuracy=("correct", "mean"), n=("correct", "size"))
            )
            byt["tournament_id"] = byt["tournament_id"].str.replace("_M_", " ", regex=False)
            st.plotly_chart(
                px.bar(
                    byt,
                    x="tournament_id",
                    y="accuracy",
                    text="n",
                    title="Elo-only accuracy on each held-out tournament (label = matches)",
                    color_discrete_sequence=[TEAL],
                ).update_layout(height=320, yaxis_tickformat=".0%"),
                width="stretch",
            )
        st.markdown("Accuracy difference against Elo-only (paired bootstrap, 95% interval):")
        table("model_evaluation/winner_comparisons.csv")
        st.caption(
            "Ties, no-results and walkovers are excluded (no winner to predict). Super Overs decide the winner of a tied match and count as results."
        )

    with tabs[1]:
        met = A.report_csv("model_evaluation/innings_projection_metrics.csv")
        gains = A.report_csv("model_evaluation/innings_projection_gains.csv")
        ipred = A.report_csv("model_evaluation/innings_projection_predictions.csv")
        if met is None:
            st.info("Run `python scripts/train_innings_projection.py`.")
        else:
            fmt2 = st.radio("Format ", ["T20", "ODI"], horizontal=True)
            by_over = met[
                (met["format"] == fmt2)
                & met["scope"].str.startswith("over")
                & met["model"].isin(
                    [
                        "baseline_run_rate",
                        "linear_regression",
                        "random_forest__remaining",
                        "gradient_boosting__remaining",
                    ]
                )
            ].copy()
            by_over["over"] = by_over["scope"].str.replace("over ", "").astype(int)
            a, b = st.columns(2)
            with a:
                st.plotly_chart(
                    px.line(
                        by_over,
                        x="over",
                        y="mae",
                        color="model",
                        markers=True,
                        title=f"{fmt2}: error of the projected final score by over (lower is better)",
                    ).update_layout(height=380),
                    width="stretch",
                )
            with b:
                piv = by_over.pivot(index="model", columns="over", values="mae")
                st.plotly_chart(
                    C.heatmap(
                        piv.to_numpy(),
                        piv.columns,
                        piv.index,
                        "MAE by model and over",
                        380,
                        C.HEAT,
                        ".1f",
                    ),
                    width="stretch",
                )
            if ipred is not None:
                at = st.select_slider(
                    "Look at overs",
                    options=sorted(ipred[ipred["format"] == fmt2]["checkpoint"].unique()),
                    value=sorted(ipred[ipred["format"] == fmt2]["checkpoint"].unique())[2],
                )
                g = ipred[(ipred["format"] == fmt2) & (ipred["checkpoint"] == at)]
                fig = px.scatter(
                    g,
                    x="y",
                    y="linear_regression",
                    hover_data=["match_id"],
                    title=f"Projected vs actual final score at over {at} (held-out tournaments)",
                    color_discrete_sequence=[TEAL],
                )
                lim = [g["y"].min(), g["y"].max()]
                fig.add_trace(
                    go.Scatter(
                        x=lim,
                        y=lim,
                        mode="lines",
                        line=dict(dash="dash", color="rgba(255,255,255,.5)"),
                        showlegend=False,
                    )
                )
                fig.update_layout(height=400, xaxis_title="actual", yaxis_title="projected")
                st.plotly_chart(fig, width="stretch")
            st.markdown(
                "Gain over run-rate extrapolation (MAE, runs; bootstrap over whole innings):"
            )
            st.dataframe(gains[gains["format"] == fmt2].round(2), hide_index=True, width="stretch")
            st.markdown("**Try it**")
            n_over = 20 if fmt2 == "T20" else 50
            c = st.columns(4)
            over = c[0].slider("Overs completed", 4, n_over - 2, 10 if fmt2 == "T20" else 25)
            score = c[1].number_input("Score", 0, 450, 85 if fmt2 == "T20" else 150)
            wk = c[2].slider("Wickets lost", 0, 9, 2)
            last5 = c[3].number_input(
                "Runs in the last 5 overs", 0, 120, 40 if fmt2 == "T20" else 32
            )
            rr = score / over
            typical = 160.0 if fmt2 == "T20" else 260.0
            feats = {
                "score": float(score),
                "wickets": wk,
                "overs": float(over),
                "run_rate": rr,
                "recent_run_rate": last5 / 5,
                "wickets_last5": 0,
                "boundary_freq": 0.12 if fmt2 == "T20" else 0.08,
                "dot_freq": 0.35 if fmt2 == "T20" else 0.5,
                "projected_linear": score + rr * (n_over - over),
                "bat_elo_diff": 0.0,
                "venue_avg_first_innings": typical,
                "bat_runs_for": typical,
                "bowl_runs_against": typical,
            }
            pr = serving.project_innings(feats, fmt2)
            cards(
                [
                    ("Model projection", f"{pr['model']:.0f}", "final total"),
                    (
                        "Run-rate projection",
                        f"{pr['run_rate_baseline']:.0f}",
                        "score + current rate",
                    ),
                ],
                [TEAL, AMBER],
            )
            st.caption(
                A.projection_crossover(fmt2)[1]
                + " Boundary and dot-ball frequencies and team context use typical values here; for a real match use the Ball-by-Ball Analytics page."
            )

    with tabs[2]:
        matches, perf = history()
        teams = Q.teams()
        names = dict(zip(teams["team_id"], teams["team_name"], strict=True))
        fmt3 = st.radio("Format  ", ["ODI", "T20"], horizontal=True)
        active = sorted(
            set(matches.loc[matches["format"] == fmt3, "team1_id"])
            | set(matches.loc[matches["format"] == fmt3, "team2_id"]),
            key=lambda t: names.get(t, t),
        )
        c = st.columns(2)
        bat = c[0].selectbox(
            "Batting first", active, format_func=lambda t: names.get(t, t), index=0, key="bat"
        )
        bowl = c[1].selectbox(
            "Bowling first",
            active,
            format_func=lambda t: names.get(t, t),
            index=min(1, len(active) - 1),
            key="bowl",
        )
        if bat == bowl:
            st.warning("Pick two different teams.")
        else:
            row = serving.hypothetical_features(matches, perf, fmt3, bat, bowl, bat_first=bat)
            pred_score = serving.predict_prematch_score(row)
            st.plotly_chart(
                C.gauge(
                    pred_score,
                    "Expected first-innings score",
                    0 if fmt3 == "T20" else 100,
                    260 if fmt3 == "T20" else 450,
                    "",
                    260,
                ),
                width="stretch",
            )
            st.caption(
                "Pre-match estimate from team strength, venue history and era (ridge regression). Typical error is about 40 runs (ODI 59, T20 28), so it is a rough guide only."
            )
        table("model_comparison/score_metrics.csv")

    with tabs[3]:
        st.markdown(
            "**Player models** (Models 3-5): consistency, role clustering and batting-performance regression. Full views: Player Analytics and Statistical Research."
        )
        a, b = st.columns(2)
        with a:
            d = A.feature_parquet("clusters_batters.parquet")
            if d is not None:
                st.plotly_chart(
                    px.scatter(
                        d,
                        x="pc1",
                        y="pc2",
                        color="cluster_label",
                        hover_name="player",
                        title="Batter clusters (PCA)",
                    ).update_layout(height=420),
                    width="stretch",
                )
        with b:
            d = A.feature_parquet("clusters_bowlers.parquet")
            if d is not None:
                st.plotly_chart(
                    px.scatter(
                        d,
                        x="pc1",
                        y="pc2",
                        color="cluster_label",
                        hover_name="player",
                        title="Bowler clusters (PCA)",
                    ).update_layout(height=420),
                    width="stretch",
                )
        for kind in ("batters", "bowlers"):
            sel = A.report_csv(f"model_evaluation/clusters_{kind}_k_selection.csv")
            if sel is not None:
                st.plotly_chart(
                    px.line(
                        sel,
                        x="k",
                        y="silhouette",
                        markers=True,
                        title=f"{kind.title()}: silhouette by k",
                    ).update_layout(height=260),
                    width="stretch",
                )

    with tabs[4]:
        a, b = st.columns(2)
        imp = A.report_csv("feature_importance/importance_winner_logistic.csv")
        shp = A.report_csv("shap_analysis/shap_global_winner.csv")
        with a:
            if imp is not None:
                d = imp.sort_values("mean_importance")
                fig = px.bar(
                    d,
                    x="mean_importance",
                    y="feature",
                    orientation="h",
                    color="family",
                    error_x="std_across_folds",
                    title="Out-of-time permutation importance (log-loss increase)",
                )
                fig.update_layout(height=470)
                st.plotly_chart(fig, width="stretch")
        with b:
            if shp is not None:
                d = shp.sort_values("mean_abs_shap")
                st.plotly_chart(
                    px.bar(
                        d,
                        x="mean_abs_shap",
                        y="feature",
                        orientation="h",
                        color="family",
                        title="Mean |SHAP| (log-odds)",
                    ).update_layout(height=470),
                    width="stretch",
                )
        ab = A.report_csv("model_comparison/ablation_winner.csv")
        if ab is not None:
            st.plotly_chart(
                px.bar(
                    ab,
                    x="feature_set",
                    y="log_loss",
                    color="accuracy",
                    color_continuous_scale="Tealgrn",
                    text="n_features",
                    title="Do extra features help? Log-loss by feature set (label = number of features)",
                ).update_layout(
                    height=340,
                    yaxis_range=[ab["log_loss"].min() - 0.01, ab["log_loss"].max() + 0.01],
                ),
                width="stretch",
            )
        st.caption(
            "Limits: about 640 labelled matches; team-strength features are correlated, so importance is shared between them; historical ball-by-ball coverage is 75%, which only affects the live-innings model."
        )

    with tabs[5]:
        sm = A.report_csv("model_comparison/score_metrics.csv")
        if wm is not None:
            allm = wm[wm["scope"] == "all"]
            fig = px.scatter(
                allm,
                x="log_loss",
                y="accuracy",
                text="model",
                size="auc",
                color="f1",
                color_continuous_scale="Tealgrn",
                title="Winner models: accuracy vs log-loss (size = AUC, colour = F1)",
            )
            fig.update_traces(textposition="top center", textfont=dict(size=9))
            fig.update_layout(height=450)
            st.plotly_chart(fig, width="stretch")
            table("model_comparison/winner_metrics.csv")
        if sm is not None:
            allm = sm[sm["scope"] == "all"]
            st.plotly_chart(
                px.bar(
                    allm,
                    x="model",
                    y=["mae", "rmse"],
                    barmode="group",
                    title="Pre-match score models: MAE and RMSE (runs)",
                ).update_layout(height=340),
                width="stretch",
            )
