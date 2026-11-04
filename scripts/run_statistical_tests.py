# ruff: noqa: E501
"""Stage 10: run the hypothesis tests and write reports/statistical_tests.md (+ CSV)."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.analytics.stats_tests import ALPHA, run_all, to_frame  # noqa: E402


def fmt_p(p: float) -> str:
    return "<0.001" if p < 0.001 else f"{p:.3f}"


def main() -> int:
    results = run_all()
    df = to_frame(results)
    out = ROOT / "reports"
    out.mkdir(exist_ok=True)
    df.to_csv(out / "statistical_tests.csv", index=False)

    lines = [
        "# Statistical tests (Stage 10)",
        "",
        f"{len(results)} hypothesis tests on the gold layer. p-values are corrected for the whole "
        f"family with Holm's method; a result is called significant only if the corrected p < {ALPHA}.",
        "",
        "**How to read this.** Matches are not independent draws (the same teams and tournaments "
        "repeat), so p-values are indicative. With large samples tiny effects become significant, so "
        "the effect size and interval matter more than the verdict.",
        "",
        "| Test | n | Effect | 95% CI | p | p (Holm) | Verdict |",
        "|---|---|---|---|---|---|---|",
    ]
    for r in results:
        ci = "" if r.ci_low is None else f"{r.ci_low:.3f} to {r.ci_high:.3f}"
        verdict = "reject H0" if r.significant else "cannot reject H0"
        lines.append(
            f"| `{r.test_id}` | {r.n:,} | {r.effect_name}: {r.effect:.3f} | {ci} | "
            f"{fmt_p(r.p_value)} | {fmt_p(r.p_adjusted)} | {verdict} |"
        )
    lines += ["", "## Hypotheses and notes", ""]
    for r in results:
        lines += [f"**`{r.test_id}`** - H0: {r.hypothesis}. Method: {r.method}. {r.note}", ""]
    (out / "statistical_tests.md").write_text("\n".join(lines), encoding="utf-8")
    print(
        df[["test_id", "n", "effect", "ci_low", "ci_high", "p_value", "p_holm"]]
        .round(4)
        .to_string(index=False)
    )
    print(f"\nsignificant after Holm: {int(df[f'significant_at_{ALPHA}'].sum())} of {len(df)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
