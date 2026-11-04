# ruff: noqa: E501
"""Reusable chart builders (Plotly) so every page looks and behaves the same."""

from __future__ import annotations

import numpy as np
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go

from app.utils.theme import (
    AMBER,
    BLUE,
    COLORWAY,
    DIVERGING,  # noqa: F401  (re-exported for the pages)
    HEAT,
    ISO3,
    PINK,
    RED,
    SEQUENTIAL,
    TEAL,
    WEST_INDIES_HOSTS,
)


def style(fig: go.Figure, height: int = 380, title: str | None = None) -> go.Figure:
    fig.update_layout(height=height)
    if title is not None:
        fig.update_layout(title=title)
    return fig


def radar(
    categories: list[str],
    series: dict[str, list[float]],
    title: str = "",
    height: int = 420,
    rng: tuple[float, float] = (0, 100),
) -> go.Figure:
    fig = go.Figure()
    for i, (name, vals) in enumerate(series.items()):
        c = COLORWAY[i % len(COLORWAY)]
        fig.add_trace(
            go.Scatterpolar(
                r=[*vals, vals[0]],
                theta=[*categories, categories[0]],
                name=name,
                fill="toself",
                line=dict(color=c, width=2.5),
                fillcolor=_alpha(c, 0.22),
            )
        )
    fig.update_layout(
        polar=dict(radialaxis=dict(range=list(rng), showticklabels=False)),
        title=title,
        height=height,
    )
    return fig


def _alpha(hex_color: str, a: float) -> str:
    h = hex_color.lstrip("#")
    r, g, b = int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
    return f"rgba({r},{g},{b},{a})"


def donut(
    labels,
    values,
    title: str = "",
    height: int = 340,
    hole: float = 0.58,
    colors: list[str] | None = None,
) -> go.Figure:
    fig = go.Figure(
        go.Pie(
            labels=labels,
            values=values,
            hole=hole,
            marker=dict(colors=colors or COLORWAY, line=dict(color="#0A0F1E", width=2)),
            textinfo="label+percent",
            sort=False,
        )
    )
    fig.update_layout(title=title, height=height, showlegend=False)
    return fig


def heatmap(
    z,
    x,
    y,
    title: str = "",
    height: int = 420,
    colorscale=None,
    fmt: str = ".0f",
    zmid: float | None = None,
    show_text: bool = True,
) -> go.Figure:
    arr = np.asarray(z, dtype=float)
    fig = go.Figure(
        go.Heatmap(
            z=arr,
            x=list(x),
            y=list(y),
            colorscale=colorscale or SEQUENTIAL,
            zmid=zmid,
            text=np.where(
                np.isnan(arr),
                "",
                np.vectorize(lambda v: format(v, fmt), otypes=[object])(np.nan_to_num(arr)),
            )
            if show_text
            else None,
            texttemplate="%{text}" if show_text else None,
            hoverongaps=False,
            xgap=2,
            ygap=2,
            colorbar=dict(thickness=10),
        )
    )
    fig.update_layout(title=title, height=height)
    fig.update_yaxes(autorange="reversed")
    return fig


def sankey(
    labels: list[str],
    source: list[int],
    target: list[int],
    value: list[float],
    title: str = "",
    height: int = 380,
    node_colors: list[str] | None = None,
) -> go.Figure:
    fig = go.Figure(
        go.Sankey(
            node=dict(
                label=labels,
                pad=18,
                thickness=16,
                color=node_colors or COLORWAY[: len(labels)],
                line=dict(color="#0A0F1E", width=1),
            ),
            link=dict(source=source, target=target, value=value, color="rgba(143,160,192,.28)"),
        )
    )
    fig.update_layout(title=title, height=height)
    return fig


def waterfall(labels, values, title: str = "", height: int = 360) -> go.Figure:
    fig = go.Figure(
        go.Waterfall(
            x=list(labels),
            y=list(values),
            measure=["relative"] * len(values),
            increasing=dict(marker=dict(color=TEAL)),
            decreasing=dict(marker=dict(color=RED)),
            connector=dict(line=dict(color="rgba(255,255,255,.25)")),
        )
    )
    fig.update_layout(title=title, height=height)
    return fig


def gauge(
    value: float,
    title: str,
    lo: float = 0,
    hi: float = 100,
    suffix: str = "",
    height: int = 230,
    color: str = TEAL,
) -> go.Figure:
    fig = go.Figure(
        go.Indicator(
            mode="gauge+number",
            value=value,
            number=dict(suffix=suffix, font=dict(size=34)),
            title=dict(text=title, font=dict(size=14)),
            gauge=dict(
                axis=dict(range=[lo, hi]),
                bar=dict(color=color, thickness=0.3),
                bgcolor="rgba(255,255,255,.05)",
                borderwidth=0,
                steps=[
                    dict(range=[lo, lo + (hi - lo) * 0.5], color="rgba(255,255,255,.04)"),
                    dict(range=[lo + (hi - lo) * 0.5, hi], color="rgba(255,255,255,.08)"),
                ],
            ),
        )
    )
    fig.update_layout(height=height, margin=dict(l=20, r=20, t=50, b=10))
    return fig


def world_map(
    hosts: list[str], title: str = "Where the World Cups were played", height: int = 420
) -> go.Figure:
    """Count tournaments per host nation. ``hosts`` are the raw host strings (semicolon separated)."""
    counts: dict[str, int] = {}
    for h in hosts:
        for name in [x.strip() for x in str(h).split(";") if x.strip()]:
            codes = WEST_INDIES_HOSTS if name == "West Indies" else [ISO3.get(name)]
            for c in codes:
                if c:
                    counts[c] = counts.get(c, 0) + 1
    df = pd.DataFrame({"iso": list(counts), "tournaments": list(counts.values())})
    fig = px.choropleth(
        df,
        locations="iso",
        color="tournaments",
        color_continuous_scale=[[0, "#1b2f63"], [0.5, BLUE], [1, AMBER]],
        projection="natural earth",
    )
    fig.update_geos(
        projection_rotation=dict(lon=35),
        bgcolor="rgba(0,0,0,0)",
        showcountries=True,
        countrycolor="rgba(255,255,255,.12)",
        showland=True,
        landcolor="#111A2E",
        showocean=True,
        oceancolor="#0A0F1E",
        showframe=False,
        lakecolor="#0A0F1E",
    )
    fig.update_layout(
        title=title,
        height=height,
        margin=dict(l=0, r=0, t=50, b=0),
        coloraxis_colorbar=dict(thickness=10, title=""),
    )
    return fig


def calendar_heat(dates: pd.Series, title: str = "", height: int = 320) -> go.Figure:
    d = pd.to_datetime(dates)
    g = (
        d.groupby([d.dt.year, d.dt.month])
        .size()
        .unstack(fill_value=0)
        .reindex(columns=range(1, 13), fill_value=0)
    )
    months = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
    return heatmap(
        g.to_numpy(),
        months,
        [str(y) for y in g.index],
        title=title,
        height=height,
        colorscale=HEAT,
        show_text=False,
    )


def lollipop(
    df: pd.DataFrame,
    label: str,
    value: str,
    color: str = BLUE,
    title: str = "",
    height: int = 380,
    fmt: str = ".0f",
) -> go.Figure:
    d = df.sort_values(value)
    fig = go.Figure()
    fig.add_trace(
        go.Scatter(
            x=d[value],
            y=d[label],
            mode="markers+text",
            marker=dict(size=13, color=color),
            text=[format(v, fmt) for v in d[value]],
            textposition="middle right",
            textfont=dict(size=11),
            showlegend=False,
        )
    )
    for _, r in d.iterrows():
        fig.add_shape(
            type="line",
            x0=0,
            x1=r[value],
            y0=r[label],
            y1=r[label],
            line=dict(color=color, width=2),
        )
    fig.update_layout(title=title, height=height, xaxis=dict(range=[0, d[value].max() * 1.18]))
    return fig


def volcano(
    df: pd.DataFrame, effect: str, p: str, label: str, title: str = "", height: int = 420
) -> go.Figure:
    d = df.copy()
    d["neglogp"] = -np.log10(d[p].clip(lower=1e-12))
    d["sig"] = np.where(d["neglogp"] > -np.log10(0.05), "significant", "not significant")
    fig = px.scatter(
        d,
        x=effect,
        y="neglogp",
        color="sig",
        hover_name=label,
        text=label,
        color_discrete_map={"significant": TEAL, "not significant": "#7d8aa8"},
    )
    fig.update_traces(textposition="top center", marker=dict(size=11), textfont=dict(size=9))
    fig.add_hline(
        y=-np.log10(0.05),
        line_dash="dash",
        line_color="rgba(255,255,255,.35)",
        annotation_text="adjusted p = 0.05",
    )
    fig.update_layout(
        title=title, height=height, yaxis_title="-log10(adjusted p)", legend_title_text=""
    )
    return fig


def roc_curves(
    pred: pd.DataFrame,
    models: list[str],
    title: str = "ROC curves (out-of-time)",
    height: int = 400,
) -> go.Figure:
    from sklearn.metrics import auc, roc_curve

    fig = go.Figure(
        go.Scatter(
            x=[0, 1],
            y=[0, 1],
            mode="lines",
            line=dict(dash="dash", color="rgba(255,255,255,.35)"),
            name="chance",
        )
    )
    for i, m in enumerate(models):
        g = pred[pred[m].notna()]
        fpr, tpr, _ = roc_curve(g["y"], g[m])
        fig.add_trace(
            go.Scatter(
                x=fpr,
                y=tpr,
                mode="lines",
                name=f"{m} (AUC {auc(fpr, tpr):.2f})",
                line=dict(width=2.5, color=COLORWAY[i % len(COLORWAY)]),
            )
        )
    fig.update_layout(
        title=title,
        height=height,
        xaxis_title="false positive rate",
        yaxis_title="true positive rate",
    )
    return fig


def confusion(y, p, title: str = "", height: int = 340) -> go.Figure:
    yy, pp = np.asarray(y).astype(int), (np.asarray(p) > 0.5).astype(int)
    m = np.array(
        [
            [((yy == 0) & (pp == 0)).sum(), ((yy == 0) & (pp == 1)).sum()],
            [((yy == 1) & (pp == 0)).sum(), ((yy == 1) & (pp == 1)).sum()],
        ]
    )
    fig = heatmap(
        m,
        ["predicted A loses", "predicted A wins"],
        ["A lost", "A won"],
        title=title,
        height=height,
        colorscale=SEQUENTIAL,
    )
    return fig


def box_violin(
    df: pd.DataFrame,
    x: str,
    y: str,
    color: str | None = None,
    title: str = "",
    height: int = 380,
    kind: str = "violin",
) -> go.Figure:
    fn = px.violin if kind == "violin" else px.box
    kw = dict(box=True, points=False) if kind == "violin" else {}
    fig = fn(df, x=x, y=y, color=color or x, **kw)
    fig.update_layout(title=title, height=height, showlegend=color is not None)
    return fig


def bubble(
    df: pd.DataFrame,
    x: str,
    y: str,
    size: str,
    color: str | None = None,
    hover: str | None = None,
    title: str = "",
    height: int = 420,
) -> go.Figure:
    fig = px.scatter(
        df, x=x, y=y, size=size, color=color, hover_name=hover, size_max=38, opacity=0.8
    )
    fig.update_layout(title=title, height=height)
    return fig


def area_line(
    df: pd.DataFrame, x: str, y: str, color: str | None = None, title: str = "", height: int = 340
) -> go.Figure:
    fig = px.area(df, x=x, y=y, color=color, markers=True)
    fig.update_layout(title=title, height=height)
    return fig


def diverging_bar(
    df: pd.DataFrame, label: str, value: str, title: str = "", height: int = 420, mid: float = 50.0
) -> go.Figure:
    d = df.sort_values(value)
    fig = go.Figure(
        go.Bar(
            x=d[value] - mid,
            y=d[label],
            orientation="h",
            marker=dict(color=np.where(d[value] >= mid, TEAL, PINK)),
            customdata=d[value],
            hovertemplate="%{y}: %{customdata:.1f}<extra></extra>",
        )
    )
    fig.update_layout(title=title, height=height, xaxis_title=f"relative to {mid:g}")
    return fig
