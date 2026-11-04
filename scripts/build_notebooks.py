# ruff: noqa: E501
"""Stage 9: build and execute the EDA notebooks (notebooks/*.ipynb) from the gold DuckDB.

    python scripts/build_notebooks.py

Notebooks are generated from the cell lists below and executed, so every chart and number stored in
them is a real output of the current data. Findings are printed by code rather than hand-typed.
"""

from __future__ import annotations

import sys
from pathlib import Path

import nbformat as nbf
from nbclient import NotebookClient

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "notebooks"

SETUP = """
import duckdb, pandas as pd, numpy as np
import matplotlib.pyplot as plt
from pathlib import Path

ROOT = Path.cwd().parent if Path.cwd().name == "notebooks" else Path.cwd()
con = duckdb.connect(str(ROOT / "data" / "warehouse" / "cricket_gold.duckdb"), read_only=True)
q = lambda sql: con.execute(sql).fetchdf()
FMT = {"ODI": "#2a6fbb", "T20": "#e07b00"}   # one colour per format, used everywhere
plt.rcParams.update({"figure.dpi": 110, "axes.spines.top": False, "axes.spines.right": False,
                     "axes.grid": True, "grid.alpha": .25, "figure.figsize": (9, 4.2)})
pd.set_option("display.width", 160)
"""

NB1 = [
    (
        "md",
        "# 01 - Tournaments and matches\nWhat the dataset contains, how matches are decided and what has changed edition by edition. Source: gold layer (`cricket_gold.duckdb`).",
    ),
    ("code", SETUP),
    ("md", "## Coverage: what data exists for each edition"),
    (
        "code",
        """
cov = q("select tournament_name, format, year, played_matches, played_with_ball_by_ball, standings_rows, teams, teams_with_squad from gold.mart_data_coverage order by format, year")
print(cov.to_string(index=False))
fig, ax = plt.subplots(figsize=(10, 4.5))
lab = cov["format"] + " " + cov["year"].astype(str)
ax.bar(lab, cov["played_with_ball_by_ball"], color="#2a6fbb", label="has ball-by-ball")
ax.bar(lab, cov["played_matches"] - cov["played_with_ball_by_ball"], bottom=cov["played_with_ball_by_ball"], color="#c9c9c9", label="scorecard only")
ax.set_ylabel("played matches"); ax.set_title("Ball-by-ball coverage by edition"); ax.legend(); plt.xticks(rotation=60)
plt.tight_layout(); plt.show()
tot, bbb = cov.played_matches.sum(), cov.played_with_ball_by_ball.sum()
print(f"FINDING: {bbb} of {tot} played matches ({100*bbb/tot:.0f}%) have ball-by-ball data; the rest are scorecard-only (source limit).")
""",
    ),
    ("md", "## How matches end"),
    (
        "code",
        """
res = q("select format, coalesce(margin_type,'unknown') as outcome, count(*) n from gold.fact_matches group by 1,2 order by 1,3 desc")
piv = res.pivot(index="outcome", columns="format", values="n").fillna(0).astype(int)
print(piv)
piv.plot.barh(color=[FMT["ODI"], FMT["T20"]], figsize=(8, 4)); plt.title("Match outcomes by format"); plt.xlabel("matches"); plt.tight_layout(); plt.show()
""",
    ),
    (
        "code",
        """
m = q("select format, margin_type, margin_value from gold.fact_matches where margin_type in ('runs','wickets')")
fig, axes = plt.subplots(1, 2, figsize=(11, 4))
for ax, kind in zip(axes, ["runs", "wickets"]):
    for f, g in m[m.margin_type == kind].groupby("format"):
        ax.hist(g.margin_value, bins=range(0, int(m[m.margin_type == kind].margin_value.max()) + 10, 10 if kind == "runs" else 1), alpha=.6, label=f, color=FMT[f])
    ax.set_title(f"Winning margin ({kind})"); ax.legend()
plt.tight_layout(); plt.show()
med = m.groupby(["format", "margin_type"]).margin_value.median()
print("FINDING: median winning margin =", med.round(1).to_dict())
""",
    ),
    ("md", "## Batting first vs chasing, and the toss"),
    (
        "code",
        '''
d = q("""select format, year, count(*) n,
  avg(case when winner_id = batting_first_team_id then 1.0 else 0 end) bat_first_win
  from gold.fact_matches where is_completed and not is_walkover and winner_id is not null group by 1,2 order by 1,2""")
fig, ax = plt.subplots()
for f, g in d.groupby("format"):
    ax.plot(g.year, 100 * g.bat_first_win, "o-", color=FMT[f], label=f)
ax.axhline(50, color="k", lw=.8, ls="--"); ax.set_ylabel("% won by team batting first"); ax.set_title("Batting-first win rate by edition"); ax.legend()
plt.show()
allr = d.assign(w=d.bat_first_win * d.n).groupby("format").apply(lambda g: g.w.sum() / g.n.sum(), include_groups=False)
print("FINDING: overall bat-first win rate =", (100 * allr).round(1).to_dict(), "(see statistical_tests.md: not distinguishable from 50%)")
''',
    ),
    (
        "code",
        '''
t = q("""select format, toss_decision, count(*) n from gold.fact_matches where toss_decision is not null group by 1,2""")
print(t.pivot(index="format", columns="toss_decision", values="n"))
y = q("""select year, format, avg(case when toss_decision='field' then 1.0 else 0 end)*100 as field_pct from gold.fact_matches where toss_decision is not null group by 1,2 order by 2,1""")
fig, ax = plt.subplots()
for f, g in y.groupby("format"):
    ax.plot(g.year, g.field_pct, "o-", color=FMT[f], label=f)
ax.set_ylabel("% choosing to field"); ax.set_title("Captains' toss decision over time"); ax.legend(); plt.show()
''',
    ),
    ("md", "## Scoring and boundaries over time"),
    (
        "code",
        """
s = q("select format, year, runs_per_match, avg_first_innings_score, sixes, matches from gold.mart_tournament_summary order by 1,2")
fig, axes = plt.subplots(1, 2, figsize=(11, 4))
for f, g in s.groupby("format"):
    axes[0].plot(g.year, g.avg_first_innings_score, "o-", color=FMT[f], label=f)
    axes[1].plot(g.year, g.sixes / g.matches, "o-", color=FMT[f], label=f)
axes[0].set_title("Average first-innings score"); axes[1].set_title("Sixes per match")
for a in axes: a.legend()
plt.tight_layout(); plt.show()
for f, g in s.groupby("format"):
    print(f"FINDING [{f}]: avg first-innings score {g.avg_first_innings_score.iloc[0]:.0f} ({g.year.iloc[0]}) -> {g.avg_first_innings_score.iloc[-1]:.0f} ({g.year.iloc[-1]}); sixes/match {g.sixes.iloc[0]/g.matches.iloc[0]:.1f} -> {g.sixes.iloc[-1]/g.matches.iloc[-1]:.1f}")
""",
    ),
]

NB2 = [
    (
        "md",
        "# 02 - Batting and bowling\nDistributions and leaders. Career figures cover World Cups from 2003 only (ODI) and all T20 editions.",
    ),
    ("code", SETUP),
    ("md", "## Innings totals"),
    (
        "code",
        """
i = q("select format, total_runs, wickets, year from gold.fact_innings where not is_super_over and total_runs is not null")
fig, axes = plt.subplots(1, 2, figsize=(11, 4))
for ax, f in zip(axes, ["ODI", "T20"]):
    g = i[i.format == f]
    ax.hist(g.total_runs, bins=25, color=FMT[f]); ax.set_title(f"{f} innings totals (n={len(g)})"); ax.set_xlabel("runs")
plt.tight_layout(); plt.show()
print(i.groupby("format").total_runs.describe().round(1))
""",
    ),
    (
        "code",
        """
fig, ax = plt.subplots(figsize=(11, 4))
t = i[i.format == "T20"]
t.boxplot(column="total_runs", by="year", ax=ax, grid=False); ax.set_title("T20 innings totals by edition"); plt.suptitle("")
plt.show()
""",
    ),
    ("md", "## Individual batting"),
    (
        "code",
        '''
p = q("""select f.runs, f.balls_faced, f.format, (not f.is_out) as not_out from gold.fact_player_performances f where f.did_bat and f.balls_faced > 0""")
fig, axes = plt.subplots(1, 2, figsize=(11, 4))
for ax, f in zip(axes, ["ODI", "T20"]):
    g = p[p.format == f]
    ax.hist(g.runs, bins=range(0, 140, 5), color=FMT[f]); ax.set_title(f"{f}: runs per innings"); ax.set_yscale("log")
plt.tight_layout(); plt.show()
for f, g in p.groupby("format"):
    print(f"FINDING [{f}]: median {g.runs.median():.0f} runs; {100*(g.runs>=50).mean():.1f}% of innings reach 50; {100*(g.runs==0).mean():.1f}% are ducks")
''',
    ),
    (
        "code",
        '''
c = q("""select p.full_name, b.format, b.balls_faced, b.runs, b.strike_rate, b.average from gold.mart_batting_career b join gold.dim_players p using (player_id) where b.balls_faced >= 300""")
fig, ax = plt.subplots(figsize=(8, 5))
for f, g in c.groupby("format"):
    ax.scatter(g.average, g.strike_rate, s=g.runs / 12, alpha=.55, color=FMT[f], label=f)
for r in c.nlargest(8, "runs").itertuples():
    ax.annotate(r.full_name.split()[-1], (r.average, r.strike_rate), fontsize=8)
ax.set_xlabel("batting average"); ax.set_ylabel("strike rate"); ax.set_title("Average vs strike rate (>= 300 balls; size = runs)"); ax.legend()
plt.show()
print("FINDING: correlation of average and strike rate:", c.groupby("format").apply(lambda g: round(g.average.corr(g.strike_rate), 2), include_groups=False).to_dict())
''',
    ),
    ("md", "## Bowling"),
    (
        "code",
        '''
b = q("""select p.full_name, w.format, w.balls_bowled, w.wickets, w.economy, w.average, w.strike_rate from gold.mart_bowling_career w join gold.dim_players p using (player_id) where w.balls_bowled >= 300""")
fig, ax = plt.subplots(figsize=(8, 5))
for f, g in b.groupby("format"):
    ax.scatter(g.economy, g.strike_rate, s=g.wickets * 4, alpha=.55, color=FMT[f], label=f)
ax.set_xlabel("economy"); ax.set_ylabel("balls per wicket (lower is better)"); ax.set_title("Economy vs strike rate (>= 300 balls; size = wickets)"); ax.legend()
plt.show()
d = q("select m.format, d.dismissal_type, count(*) n from gold.fact_deliveries d join gold.fact_matches m using(match_id) where d.is_wicket and not d.is_super_over group by 1,2")
d["pct"] = 100 * d.n / d.groupby("format").n.transform("sum")
print(d.pivot(index="dismissal_type", columns="format", values="pct").round(1).sort_values("ODI", ascending=False))
''',
    ),
    (
        "code",
        '''
w = q("select format, wickets, count(*) n from gold.fact_player_performances where did_bowl group by 1,2 order by 1,2")
print(w.pivot(index="wickets", columns="format", values="n").fillna(0).astype(int))
top = q("""select p.full_name, count(*) n from gold.fact_player_performances f join gold.dim_players p using(player_id) where f.wickets >= 4 group by 1 order by 2 desc limit 8""")
print("FINDING: bowlers with most 4+ wicket innings:", dict(zip(top.full_name, top.n)))
''',
    ),
]

NB3 = [
    (
        "md",
        "# 03 - Phases of play and venues\nBall-by-ball analysis (only matches that have it) and ground effects. Super Overs excluded.",
    ),
    ("code", SETUP),
    ("md", "## Run rate and dot balls by phase"),
    (
        "code",
        '''
ph = q("""select format, phase, 6.0*sum(total_runs)/count(*) filter (where is_legal_ball) as run_rate,
  100.0*avg(case when is_dot_ball then 1.0 else 0 end) as dot_pct, 100.0*avg(case when is_boundary then 1.0 else 0 end) as boundary_pct,
  100.0*avg(case when is_wicket then 1.0 else 0 end) as wicket_pct, count(*) balls
  from gold.fact_deliveries where not is_super_over and phase in ('powerplay','middle','death') group by 1,2""")
order = {"powerplay": 0, "middle": 1, "death": 2}
ph = ph.sort_values(["format", "phase"], key=lambda s: s.map(order) if s.name == "phase" else s)
print(ph.round(2).to_string(index=False))
fig, axes = plt.subplots(1, 3, figsize=(13, 4))
for ax, col, ttl in zip(axes, ["run_rate", "dot_pct", "wicket_pct"], ["Run rate (per over)", "Dot balls (%)", "Wicket balls (%)"]):
    for f, g in ph.groupby("format"):
        ax.plot(g.phase, g[col], "o-", color=FMT[f], label=f)
    ax.set_title(ttl); ax.legend()
plt.tight_layout(); plt.show()
''',
    ),
    (
        "code",
        '''
ov = q("""select format, over_number, 6.0*sum(total_runs)/count(*) filter (where is_legal_ball) rr, 100.0*avg(case when is_wicket then 1.0 else 0 end)*6 wk_per_over
  from gold.fact_deliveries where not is_super_over and ((format='T20' and over_number<=20) or (format='ODI' and over_number<=50)) group by 1,2 order by 1,2""")
fig, axes = plt.subplots(1, 2, figsize=(12, 4))
for ax, f in zip(axes, ["T20", "ODI"]):
    g = ov[ov.format == f]; ax.bar(g.over_number, g.rr, color=FMT[f]); ax.set_title(f"{f}: run rate by over"); ax.set_xlabel("over")
plt.tight_layout(); plt.show()
t = ov[ov.format == "T20"].set_index("over_number").rr
print(f"FINDING [T20]: fastest over on average is over {t.idxmax()} ({t.max():.1f} rpo); slowest is over {t.idxmin()} ({t.min():.1f} rpo)")
''',
    ),
    ("md", "## Venues"),
    (
        "code",
        """
v = q("select venue_name, city, format, matches, avg_first_innings_runs, bat_first_win_pct from dbt_analytics.an_venue_profile where matches >= 8 order by format, avg_first_innings_runs desc")
fig, axes = plt.subplots(1, 2, figsize=(13, 5))
for ax, f in zip(axes, ["ODI", "T20"]):
    g = v[v.format == f].sort_values("avg_first_innings_runs")
    ax.barh(g.venue_name.str.slice(0, 30), g.avg_first_innings_runs, color=FMT[f]); ax.set_title(f"{f}: average first-innings score (>= 8 matches)")
plt.tight_layout(); plt.show()
for f, g in v.groupby("format"):
    hi, lo = g.iloc[0], g.iloc[-1]
    print(f"FINDING [{f}]: highest-scoring ground {hi.venue_name} ({hi.avg_first_innings_runs:.0f}); lowest {lo.venue_name} ({lo.avg_first_innings_runs:.0f}); spread {hi.avg_first_innings_runs-lo.avg_first_innings_runs:.0f} runs")
""",
    ),
    (
        "code",
        '''
x = q("""select f.format, f.target, (f.winner_id = f.batting_second_team_id)::int chased from gold.fact_matches f
  where is_completed and not is_dls and not is_tie and winner_id is not null and target is not null""")
fig, axes = plt.subplots(1, 2, figsize=(11, 4))
for ax, f in zip(axes, ["ODI", "T20"]):
    g = x[x.format == f].copy(); g["bin"] = pd.qcut(g.target, 6, duplicates="drop")
    r = g.groupby("bin", observed=True).chased.agg(["mean", "count"])
    ax.bar(range(len(r)), 100 * r["mean"], color=FMT[f]); ax.set_xticks(range(len(r))); ax.set_xticklabels([f"{int(b.left)}-{int(b.right)}" for b in r.index], rotation=30)
    ax.set_title(f"{f}: chase success by target size"); ax.set_ylabel("% chases won")
plt.tight_layout(); plt.show()
''',
    ),
    (
        "md",
        "## Data-quality caveat\nEverything on this page that uses deliveries covers only matches with ball-by-ball data. Compare with notebook 01, which shows coverage by edition.",
    ),
    (
        "code",
        """
c = q("select sum(played_with_ball_by_ball) with_bbb, sum(played_matches) played from gold.mart_data_coverage")
print(f"Ball-by-ball based analysis covers {int(c.with_bbb[0])} of {int(c.played[0])} played matches.")
""",
    ),
]


def build(name: str, cells: list[tuple[str, str]]) -> Path:
    nb = nbf.v4.new_notebook()
    nb["cells"] = [
        nbf.v4.new_markdown_cell(src) if kind == "md" else nbf.v4.new_code_cell(src.strip())
        for kind, src in cells
    ]
    nb["metadata"]["kernelspec"] = {
        "name": "python3",
        "display_name": "Python 3",
        "language": "python",
    }
    NotebookClient(
        nb, timeout=300, kernel_name="python3", resources={"metadata": {"path": str(OUT)}}
    ).execute()
    path = OUT / f"{name}.ipynb"
    nbf.write(nb, path)
    return path


def main() -> int:
    OUT.mkdir(exist_ok=True)
    for name, cells in (
        ("01_tournaments_and_matches", NB1),
        ("02_batting_and_bowling", NB2),
        ("03_phases_and_venues", NB3),
    ):
        path = build(name, cells)
        print("built", path.relative_to(ROOT))
    return 0


if __name__ == "__main__":
    sys.exit(main())
