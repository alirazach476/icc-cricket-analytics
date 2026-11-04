# ruff: noqa: E501, E702
"""Stage 13: interpretability report -> reports/interpretability.md, reports/figures/*.png, CSVs."""

from __future__ import annotations

import sys
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import pandas as pd  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.ml import explain as ex  # noqa: E402

COLORS = {
    "team strength": "#2a6fbb",
    "head to head": "#7b5ea7",
    "venue": "#2b9a6b",
    "context": "#888888",
    "toss": "#e07b00",
    "other": "#bbbbbb",
}


def md(df: pd.DataFrame, nd: int = 3) -> str:
    cols = list(df.columns)
    out = ["| " + " | ".join(cols) + " |", "|" + "---|" * len(cols)]
    for r in df.itertuples(index=False):
        out.append(
            "| " + " | ".join(f"{v:.{nd}f}" if isinstance(v, float) else str(v) for v in r) + " |"
        )
    return "\n".join(out)


def bar(df: pd.DataFrame, value: str, title: str, path: Path, xlabel: str) -> None:
    d = df.sort_values(value)
    fig, ax = plt.subplots(figsize=(7, 4.2))
    ax.barh(d["feature"], d[value], color=[COLORS[f] for f in d["family"]])
    ax.set_title(title)
    ax.set_xlabel(xlabel)
    ax.axvline(0, color="k", lw=0.7)
    handles = [plt.Rectangle((0, 0), 1, 1, color=c) for c in COLORS.values() if c]
    ax.legend(handles, list(COLORS), fontsize=7, loc="lower right")
    for s in ("top", "right"):
        ax.spines[s].set_visible(False)
    fig.tight_layout()
    fig.savefig(path, dpi=130)
    plt.close(fig)


def main() -> int:
    feats = pd.read_parquet(ROOT / "data" / "features" / "match_features.parquet")
    rep = ROOT / "reports"
    fi_dir, shap_dir, cmp_dir = rep / "feature_importance", rep / "shap_analysis", rep / "model_comparison"
    for d in (fi_dir, shap_dir, cmp_dir):
        d.mkdir(parents=True, exist_ok=True)

    perm_w = ex.permutation_importance_oot(feats, "winner", "logistic")
    perm_rf = ex.permutation_importance_oot(feats, "winner", "random_forest", repeats=8)
    perm_s = ex.permutation_importance_oot(feats, "score", "ridge")
    model, labelled = ex.fit_logistic(feats)
    gs = ex.global_shap(model, labelled)
    for name, df in (
        ("winner_logistic", perm_w),
        ("winner_random_forest", perm_rf),
        ("score_ridge", perm_s),
    ):
        df.to_csv(fi_dir / f"importance_{name}.csv", index=False)
    gs.to_csv(shap_dir / "shap_global_winner.csv", index=False)

    bar(
        perm_w,
        "mean_importance",
        "Winner model: out-of-time permutation importance",
        fi_dir / "importance_winner.png",
        "log-loss increase when shuffled",
    )
    bar(
        perm_s,
        "mean_importance",
        "Score model: out-of-time permutation importance",
        fi_dir / "importance_score.png",
        "MAE increase (runs) when shuffled",
    )
    bar(
        gs,
        "mean_abs_shap",
        "Winner model: mean |SHAP| (log-odds)",
        shap_dir / "shap_winner.png",
        "mean |SHAP|",
    )

    examples = []
    for mid_label, mid in (
        ("most lopsided pairing", labelled.loc[labelled["elo_diff"].abs().idxmax(), "match_id"]),
        ("closest pairing", labelled.loc[labelled["elo_diff"].abs().idxmin(), "match_id"]),
        ("latest decided match", labelled.sort_values("match_date").iloc[-1]["match_id"]),
    ):
        e = ex.explain_match(model, labelled, str(mid))
        row = labelled[labelled.match_id == mid].iloc[0]
        examples.append((mid_label, mid, row, e))
    dep = ex.dependence_on_elo(model, labelled)
    corr = ex.feature_correlations(feats)
    fam = ex.family_importance(perm_w)
    abl = ex.ablation(feats)
    abl.to_csv(cmp_dir / "ablation_winner.csv", index=False)

    L = [
        "# Interpretability (Stage 13)",
        "",
        "Two lenses on the models from Stage 12. **Permutation importance** is out-of-time: each feature is shuffled in held-out future tournaments and we record how much worse the model gets. **SHAP** explains individual predictions of the saved logistic model in log-odds (additive: base + contributions = the model's log-odds).",
        "",
        "## What drives the winner model",
        "",
        md(perm_w.drop(columns=["folds"])),
        "",
        "![importance](feature_importance/importance_winner.png)",
        "",
        "By feature family (sum of importance):",
        "",
        md(fam),
        "",
        "Cross-check with a different model (random forest):",
        "",
        md(perm_rf.head(6).drop(columns=["folds"])),
        "",
        "## Which feature sets actually help? (out-of-time ablation)",
        "",
        "Permutation importance shows what the model *relies on*; this table shows what *helps*. Same expanding-window protocol, logistic model, different inputs:",
        "",
        md(abl),
        "",
        "## Global SHAP (logistic model, all labelled matches)",
        "",
        md(gs),
        "",
        "![shap](shap_analysis/shap_winner.png)",
        "",
        "## Win probability as Elo gap changes (other features at their median)",
        "",
        md(dep),
        "",
        "## Explaining individual matches",
        "",
    ]
    for label, mid, row, e in examples:
        L += [
            f"**{label}** - match `{mid}` ({str(row['match_date'])[:10]}, {row['format']}): model gives team A {e.attrs['prob_team_a']:.1%} (base log-odds {e.attrs['base_log_odds']:.2f}); actual: team A {'won' if row['y_a_wins'] == 1 else 'lost'}.",
            "",
            md(e),
            "",
        ]
    L += [
        "## What drives the score model",
        "",
        md(perm_s.drop(columns=["folds"])),
        "",
        "![importance](feature_importance/importance_score.png)",
        "",
        "## Reading these results honestly",
        "",
        "* Elo, win rate, form and runs are different measurements of the same thing (team strength): the correlation table below shows it. Importance is shared among them, so read the **family** table too.",
        "* `positive_folds` counts how many of the test tournaments the feature helped; a feature that helps in few folds is not reliable.",
        "* Importance says what the model *uses*, not what *causes* wins. Toss and year are controls, not levers.",
        "* ~640 matches: small importances (under about 0.002 log-loss) are within noise.",
        "",
        "### Feature correlations",
        "",
        md(corr.reset_index().rename(columns={"index": "feature"}), 2),
        "",
    ]
    (rep / "interpretability.md").write_text("\n".join(L), encoding="utf-8")
    print(abl.round(4).to_string(index=False))
    print()
    print(perm_w.round(4).to_string(index=False))
    print()
    print(fam.round(4).to_string(index=False))
    print()
    print(gs.round(3).head(6).to_string(index=False))
    print()
    print(perm_s.round(3).to_string(index=False))
    print()
    print(dep.round(3).to_string(index=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
