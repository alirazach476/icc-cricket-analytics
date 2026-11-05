# ruff: noqa: E501
"""Data engineering: pipeline status, freshness, inventory, quality, missing data, validation, lineage."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import pandas as pd  # noqa: E402
import plotly.express as px  # noqa: E402
import plotly.graph_objects as go  # noqa: E402
import streamlit as st  # noqa: E402
from app.utils import analytics as A  # noqa: E402
from app.utils import charts as C  # noqa: E402
from app.utils import queries as Q  # noqa: E402
from app.utils.theme import AMBER, BLUE, PINK, RED, TEAL, cards  # noqa: E402
from app.utils.ui import setup  # noqa: E402

LINEAGE = """
digraph G {
  rankdir=LR; bgcolor="transparent"; node [shape=box, style="rounded,filled", fillcolor="#16213d", color="#2b3b66", fontcolor="#E8EEF9", fontsize=10]; edge [color="#8FA0C0"];
  espn [label="ESPNcricinfo\\n(scorecards, standings, squads)"];
  cs [label="Cricsheet\\n(ball-by-ball)"];
  cfg [label="config/*.csv\\n(reviewed overrides)"];
  raw [label="data/raw + processed\\n(never modified)"];
  bronze [label="Bronze\\n(immutable, hashed)", fillcolor="#6b3f1f"];
  silver [label="Silver\\n(cleaned, identities unified)", fillcolor="#3b4a63"];
  gold [label="Gold\\n(dims, facts, marts, squads)", fillcolor="#7a6a1a"];
  pg [label="PostgreSQL\\nanalytics schema", shape=cylinder];
  dk [label="DuckDB gold", shape=cylinder];
  dbt [label="dbt models + tests"]; sql [label="SQL analytics"]; stats [label="Statistical tests"];
  feat [label="Features"]; ml [label="Models"]; app [label="This dashboard", fillcolor="#1f5a52"]; rep [label="Reports"];
  espn -> raw; cs -> raw; raw -> bronze; cfg -> bronze; bronze -> silver -> gold; gold -> pg; gold -> dk;
  dk -> dbt; dk -> sql; dk -> stats; dk -> feat -> ml; dk -> app; ml -> app; sql -> rep; stats -> rep; ml -> rep;
}
"""

if setup(
    "Data Engineering",
    "🛠️",
    "Pipeline status, freshness, inventory, quality, missing data, validation failures and lineage.",
    ["medallion architecture", "idempotent loads", "quality gates"],
):
    run_rec = A.report_json("pipeline_run.json")
    q = A.data_quality_score()
    if run_rec:
        cards(
            [
                ("Last run", run_rec["run_id"][:8] + "...", run_rec["run_id"]),
                (
                    "Result",
                    "success" if run_rec["success"] else "failed",
                    f"{len(run_rec['steps'])} steps",
                ),
                ("Quality score", "n/a" if q is None else f"{q:.1f} / 100", "gold rules"),
                ("Total time", f"{sum(s['seconds'] for s in run_rec['steps']):.0f}s", "end to end"),
            ],
            [TEAL if run_rec["success"] else RED, BLUE, AMBER, PINK],
        )
    tabs = st.tabs(
        [
            "Pipeline",
            "Freshness and inventory",
            "Data quality",
            "Missing data",
            "Validation failures",
            "Lineage",
            "Coverage",
        ]
    )

    with tabs[0]:
        if run_rec is None:
            st.info("No pipeline run recorded yet: `python scripts/run_lakehouse_pipeline.py`.")
        else:
            c = st.columns(3)
            c[0].metric("Last run", run_rec["run_id"])
            c[1].metric("Result", "success" if run_rec["success"] else "failed")
            c[2].metric("Steps", len(run_rec["steps"]))
            steps = pd.DataFrame(run_rec["steps"])[["name", "status", "seconds", "message"]]
            steps["seconds"] = steps["seconds"].round(1)
            steps["start"] = steps["seconds"].cumsum() - steps["seconds"]
            a, b = st.columns(2)
            with a:
                fig = go.Figure()
                for r in steps.itertuples():
                    fig.add_trace(
                        go.Bar(
                            x=[r.seconds],
                            y=[r.name],
                            base=[r.start],
                            orientation="h",
                            marker_color=TEAL if r.status == "ok" else RED,
                            name=r.status,
                            showlegend=False,
                            hovertext=f"{r.name}: {r.seconds}s",
                        )
                    )
                fig.update_layout(
                    title="Pipeline timeline (Gantt, seconds)",
                    height=480,
                    yaxis=dict(autorange="reversed"),
                )
                st.plotly_chart(fig, width="stretch")
            with b:
                st.plotly_chart(
                    px.pie(
                        steps,
                        names="name",
                        values="seconds",
                        hole=0.55,
                        title="Share of total time",
                    ).update_layout(height=480),
                    width="stretch",
                )
            st.dataframe(steps.drop(columns="start"), hide_index=True, width="stretch")
            if run_rec.get("dry_run"):
                st.warning("The last recorded run was a dry run (nothing executed).")
        st.caption(
            "Transformation status = the steps above: bronze, silver and gold are rebuilt from collected files; every step is idempotent."
        )

        hist = A.report_csv("pipeline_run_history.csv")
        if hist is not None and len(hist):
            st.subheader("Pipeline run history")
            hh = hist.assign(label=hist["run_id"].astype(str), result=hist["success"].map({True: "success", False: "failed"}))
            fig = px.bar(hh, x="label", y="total_seconds", color="result", color_discrete_map={"success": TEAL, "failed": RED}, text=hh["total_seconds"].round(0), hover_data=["steps_ok", "steps_failed", "started_at"], title="Processing time of each pipeline run (seconds)", labels={"label": "Run", "total_seconds": "Seconds"})
            fig.update_layout(height=340)
            st.plotly_chart(fig, width="stretch")
            if len(hist) < 3:
                st.caption("History starts with the first recorded run and grows by one row for every pipeline run (reports/pipeline_run_history.csv).")

    with tabs[1]:
        a, b = st.columns(2)
        with a:
            st.markdown("**Data freshness**")
            st.dataframe(A.file_freshness(), hide_index=True, width="stretch")
        with b:
            st.markdown("**Bronze batches (latest per entity)**")
            bm = A.bronze_manifest()
            if len(bm):
                st.dataframe(bm, hide_index=True, width="stretch")
            else:
                st.info("No bronze manifest.")
        inv = A.inventory()
        a, b = st.columns(2)
        with a:
            fig = px.treemap(
                inv.assign(kind=inv["table"].str.split("_").str[0]),
                path=["kind", "table"],
                values="rows",
                color="columns",
                color_continuous_scale="Tealgrn",
                title="Gold inventory (area = rows, colour = columns)",
            )
            fig.update_layout(height=430, margin=dict(l=4, r=4, t=50, b=4))
            st.plotly_chart(fig, width="stretch")
        with b:
            st.plotly_chart(
                px.bar(
                    inv.sort_values("rows"),
                    x="rows",
                    y="table",
                    orientation="h",
                    log_x=True,
                    color="columns",
                    color_continuous_scale="Sunsetdark",
                    title="Rows per gold table (log scale)",
                ).update_layout(height=430),
                width="stretch",
            )
        if len(bm):
            st.plotly_chart(
                px.bar(
                    bm.sort_values("rows"),
                    x="rows",
                    y="entity",
                    orientation="h",
                    log_x=True,
                    title="Rows per bronze entity (log scale)",
                    color_discrete_sequence=[AMBER],
                ).update_layout(height=420),
                width="stretch",
            )

    with tabs[2]:
        sc = A.report_csv("gold/data_quality/dataset_scores.csv")
        if sc is None:
            st.info("Run the quality step.")
        else:
            dims = [
                "completeness",
                "uniqueness",
                "validity",
                "referential_integrity",
                "consistency",
                "historical_coverage",
            ]
            a, b = st.columns([2, 3])
            with a:
                st.plotly_chart(
                    C.gauge(
                        float(sc["overall"].mean()),
                        "Mean overall quality score",
                        90,
                        100,
                        " / 100",
                        280,
                    ),
                    width="stretch",
                )
                st.dataframe(
                    sc[["dataset", "overall", "rules_evaluated", "rules_failing"]],
                    hide_index=True,
                    width="stretch",
                )
            with b:
                hm = sc.set_index("dataset")[dims]
                st.plotly_chart(
                    C.heatmap(
                        hm.to_numpy(),
                        [d.replace("_", " ") for d in dims],
                        hm.index,
                        "Quality score by dataset and dimension (blank = no rule)",
                        380,
                        C.SEQUENTIAL,
                        ".1f",
                    ),
                    width="stretch",
                )
            long = sc.melt(
                id_vars="dataset", value_vars=dims, var_name="dimension", value_name="score"
            ).dropna()
            st.plotly_chart(
                px.bar(
                    long,
                    x="dataset",
                    y="score",
                    color="dimension",
                    barmode="group",
                    title="Score by dataset and dimension",
                ).update_layout(height=380, yaxis_range=[min(90, long["score"].min() - 1), 100.5]),
                width="stretch",
            )
            rr = A.report_csv("gold/data_quality/rule_results.csv")
            if rr is not None:
                pooled = rr.groupby(["rule_id", "severity"], as_index=False)[
                    ["total", "failed"]
                ].sum()
                pooled["pass_rate"] = 100 * (1 - pooled["failed"] / pooled["total"])
                st.plotly_chart(
                    px.bar(
                        pooled.sort_values("pass_rate"),
                        x="pass_rate",
                        y="rule_id",
                        color="severity",
                        orientation="h",
                        title="Pass rate of every rule",
                        color_discrete_map={"critical": RED, "major": AMBER, "minor": BLUE},
                    ).update_layout(
                        height=620, xaxis_range=[min(70, pooled["pass_rate"].min() - 2), 100.5]
                    ),
                    width="stretch",
                )

    with tabs[3]:
        inv = A.inventory()
        table = st.selectbox("Gold table", inv["table"].tolist(), index=5)
        nulls = A.null_profile(table)
        a, b = st.columns(2)
        with a:
            if (nulls["null_pct"] > 0).any():
                st.plotly_chart(
                    px.bar(
                        nulls[nulls["null_pct"] > 0].head(25),
                        x="null_pct",
                        y="column",
                        orientation="h",
                        title=f"Missing values in {table} (% of rows)",
                        color_discrete_sequence=[PINK],
                    ).update_layout(height=470),
                    width="stretch",
                )
            else:
                st.success("No missing values in this table.")
        with b:
            st.dataframe(nulls, hide_index=True, width="stretch", height=470)
        key_tables = [
            "fact_matches",
            "fact_player_performances",
            "fact_deliveries",
            "fact_innings",
            "fact_squads",
            "dim_players",
        ]
        mat = {}
        for tb in key_tables:
            n = A.null_profile(tb)
            mat[tb] = n.set_index("column")["null_pct"]
        top_cols = sorted({c for tb in key_tables for c in mat[tb][mat[tb] > 0].nlargest(8).index})
        if top_cols:
            z = pd.DataFrame({tb: mat[tb].reindex(top_cols) for tb in key_tables}).T
            st.plotly_chart(
                C.heatmap(
                    z.to_numpy(),
                    top_cols,
                    z.index,
                    "Where data is missing across the main tables (% null)",
                    360,
                    C.HEAT,
                    ".0f",
                ),
                width="stretch",
            )
        st.caption(
            "Many nulls are legitimate, e.g. winner on a tie, or delivery-derived columns where no ball-by-ball exists."
        )

    with tabs[4]:
        rr = A.report_csv("gold/data_quality/rule_results.csv")
        if rr is not None:
            fails = rr.groupby(["rule_id", "severity", "description"], as_index=False)[
                ["total", "failed"]
            ].sum()
            fails = fails[fails["failed"] > 0]
            cards(
                [
                    ("Rules evaluated", str(rr["rule_id"].nunique()), "gold layer"),
                    ("Rules with failures", str(len(fails)), "all explained in the report"),
                    (
                        "Critical failures",
                        str(int((fails["severity"] == "critical").sum())),
                        "within documented allowance",
                    ),
                ],
                [TEAL, AMBER, RED],
            )
            st.plotly_chart(
                px.bar(
                    fails.assign(share=100 * fails["failed"] / fails["total"]),
                    x="rule_id",
                    y="failed",
                    color="severity",
                    text="failed",
                    title="Rows failing each rule",
                    log_y=True,
                    color_discrete_map={"critical": RED, "major": AMBER, "minor": BLUE},
                ).update_layout(height=360),
                width="stretch",
            )
            st.dataframe(fails, hide_index=True, width="stretch")
            st.caption(
                "Each failing rule is explained in reports/data_quality_report.md; the pipeline gate allows only documented, bounded residuals."
            )
        dup = A.report_csv("duplicate_records_report.csv")
        if dup is not None and len(dup):
            dl = dup.melt(id_vars=["dataset", "rows"], value_vars=["duplicate_key_rows", "fully_duplicated_rows", "duplicate_rows_ignoring_keys"], var_name="kind", value_name="rows_affected")
            dl["kind"] = dl["kind"].str.replace("_", " ")
            fig = px.bar(dl, x="dataset", y="rows_affected", color="kind", barmode="group", text="rows_affected", title="Duplicate records by table (0 = none found)", labels={"rows_affected": "Rows affected", "dataset": "Table"})
            fig.update_layout(height=360, xaxis_tickangle=-30)
            st.plotly_chart(fig, width="stretch")
            st.caption(f"{int(dup['rows'].sum()):,} rows checked across {len(dup)} tables for duplicate keys and fully duplicated rows.")

    with tabs[5]:
        st.graphviz_chart(LINEAGE)

    with tabs[6]:
        cov = Q.coverage()
        cov["label"] = cov["format"] + " " + cov["year"].astype(str)
        cov["scorecard_only"] = cov["played_matches"] - cov["with_bbb"]
        long = cov.melt(
            id_vars=["label"],
            value_vars=["with_bbb", "scorecard_only"],
            var_name="data",
            value_name="matches",
        )
        st.plotly_chart(
            px.bar(
                long,
                x="label",
                y="matches",
                color="data",
                color_discrete_map={"with_bbb": BLUE, "scorecard_only": "#51607f"},
                title="Ball-by-ball coverage of played matches",
            ).update_layout(height=400, xaxis_tickangle=-50),
            width="stretch",
        )
        a, b = st.columns(2)
        with a:
            gr = Q.gap_reasons()
            st.plotly_chart(
                C.donut(gr["status"], gr["matches"], "Why matches lack ball-by-ball data", 360),
                width="stretch",
            )
        with b:
            piv = cov.pivot_table(index="format", columns="year", values="coverage_pct")
            st.plotly_chart(
                C.heatmap(
                    piv.to_numpy(),
                    piv.columns,
                    piv.index,
                    "Coverage % by edition",
                    300,
                    C.SEQUENTIAL,
                    ".0f",
                ),
                width="stretch",
            )
        st.dataframe(
            cov.drop(columns=["label", "scorecard_only"]), hide_index=True, width="stretch"
        )
        st.caption(
            "Pitch, weather and day/night were never collected; any such fields in this app are labelled synthetic."
        )
