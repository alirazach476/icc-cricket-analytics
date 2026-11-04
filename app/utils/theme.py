# ruff: noqa: E501
"""Visual identity: colours, CSS, Plotly template, flags and small HTML components."""

from __future__ import annotations

import plotly.graph_objects as go
import plotly.io as pio
import streamlit as st

BG, PANEL, BORDER, TEXT, MUTED = "#0A0F1E", "#111A2E", "#1F2B47", "#E8EEF9", "#8FA0C0"
TEAL, BLUE, AMBER, PINK, VIOLET, GREEN, RED, CYAN = (
    "#22D3B6",
    "#4C8DFF",
    "#FFB020",
    "#FF5C8A",
    "#9B7BFF",
    "#6BDB6B",
    "#FF6B6B",
    "#38E1FF",
)
FORMAT_COLORS = {"ODI": BLUE, "T20": AMBER, "Test": PINK}
COLORWAY = [BLUE, AMBER, TEAL, PINK, VIOLET, GREEN, CYAN, RED, "#C58BFF", "#FFD166"]
DIVERGING = [[0, RED], [0.5, "#1b2540"], [1, TEAL]]
SEQUENTIAL = [[0, "#101a33"], [0.35, "#1f4fa3"], [0.7, BLUE], [1, CYAN]]
HEAT = [[0, "#101a33"], [0.4, "#6b3fa0"], [0.75, PINK], [1, AMBER]]

FLAGS = {
    "Afghanistan": "🇦🇫",
    "Australia": "🇦🇺",
    "Bangladesh": "🇧🇩",
    "Bermuda": "🇧🇲",
    "Canada": "🇨🇦",
    "England": "🏴󠁧󠁢󠁥󠁮󠁧󠁿",
    "Hong Kong": "🇭🇰",
    "India": "🇮🇳",
    "Ireland": "🇮🇪",
    "Italy": "🇮🇹",
    "Kenya": "🇰🇪",
    "Namibia": "🇳🇦",
    "Nepal": "🇳🇵",
    "Netherlands": "🇳🇱",
    "New Zealand": "🇳🇿",
    "Oman": "🇴🇲",
    "Pakistan": "🇵🇰",
    "Papua New Guinea": "🇵🇬",
    "Scotland": "🏴󠁧󠁢󠁳󠁣󠁴󠁿",
    "South Africa": "🇿🇦",
    "Sri Lanka": "🇱🇰",
    "Uganda": "🇺🇬",
    "United Arab Emirates": "🇦🇪",
    "United States of America": "🇺🇸",
    "West Indies": "🌴",
    "Zimbabwe": "🇿🇼",
}
# ISO-3 codes for the world map (West Indies shown through its host nations).
ISO3 = {
    "India": "IND",
    "Sri Lanka": "LKA",
    "Bangladesh": "BGD",
    "Australia": "AUS",
    "New Zealand": "NZL",
    "England": "GBR",
    "Wales": "GBR",
    "South Africa": "ZAF",
    "Kenya": "KEN",
    "Zimbabwe": "ZWE",
    "United Arab Emirates": "ARE",
    "Oman": "OMN",
    "United States": "USA",
    "West Indies": "JAM",
    "Pakistan": "PAK",
    "Afghanistan": "AFG",
    "Ireland": "IRL",
    "Scotland": "GBR",
    "Netherlands": "NLD",
    "Canada": "CAN",
    "Nepal": "NPL",
    "Namibia": "NAM",
    "Uganda": "UGA",
    "Italy": "ITA",
    "Bermuda": "BMU",
    "Hong Kong": "HKG",
    "Papua New Guinea": "PNG",
    "United States of America": "USA",
}
WEST_INDIES_HOSTS = ["JAM", "BRB", "TTO", "GUY", "LCA", "ATG", "KNA", "GRD", "VCT", "DMA"]


ISO2 = {
    "Afghanistan": "af",
    "Australia": "au",
    "Bangladesh": "bd",
    "Bermuda": "bm",
    "Canada": "ca",
    "England": "gb-eng",
    "Hong Kong": "hk",
    "India": "in",
    "Ireland": "ie",
    "Italy": "it",
    "Kenya": "ke",
    "Namibia": "na",
    "Nepal": "np",
    "Netherlands": "nl",
    "New Zealand": "nz",
    "Oman": "om",
    "Pakistan": "pk",
    "Papua New Guinea": "pg",
    "Scotland": "gb-sct",
    "South Africa": "za",
    "Sri Lanka": "lk",
    "Uganda": "ug",
    "United Arab Emirates": "ae",
    "United States of America": "us",
    "Zimbabwe": "zw",
}


def flag(team: str) -> str:
    """Plain-text flag. Windows browsers do not render flag emoji (they show letter pairs), so this is empty."""
    return ""


def flag_html(team: str, height: int = 18) -> str:
    """Small flag image for HTML contexts (needs internet; falls back to nothing)."""
    code = ISO2.get(team)
    if not code:
        return ""
    return f'<img src="https://flagcdn.com/h40/{code}.png" height="{height}" style="border-radius:3px;vertical-align:-3px;margin-right:6px">'


def plotly_template() -> go.layout.Template:
    t = go.layout.Template()
    t.layout = go.Layout(
        font=dict(family="Inter, Segoe UI, sans-serif", color=TEXT, size=13),
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        colorway=COLORWAY,
        title=dict(
            font=dict(size=17, color=TEXT),
            x=0.01,
            xanchor="left",
            y=0.97,
            yanchor="top",
            yref="container",
        ),
        margin=dict(l=40, r=20, t=92, b=40),
        xaxis=dict(
            gridcolor="rgba(255,255,255,.07)",
            zerolinecolor="rgba(255,255,255,.15)",
            linecolor="rgba(255,255,255,.15)",
            automargin=True,
        ),
        yaxis=dict(
            gridcolor="rgba(255,255,255,.07)",
            zerolinecolor="rgba(255,255,255,.15)",
            linecolor="rgba(255,255,255,.15)",
            automargin=True,
        ),
        legend=dict(
            bgcolor="rgba(0,0,0,0)",
            orientation="h",
            yanchor="bottom",
            y=1.0,
            xanchor="left",
            x=0,
            font=dict(size=11),
        ),
        hoverlabel=dict(bgcolor="#16213d", font=dict(color=TEXT), bordercolor=BORDER),
        colorscale=dict(sequential=SEQUENTIAL, diverging=DIVERGING),
        polar=dict(
            bgcolor="rgba(0,0,0,0)",
            radialaxis=dict(gridcolor="rgba(255,255,255,.12)", linecolor="rgba(255,255,255,.12)"),
            angularaxis=dict(gridcolor="rgba(255,255,255,.12)"),
        ),
    )
    return t


def register_plotly() -> None:
    pio.templates["cwc"] = plotly_template()
    pio.templates.default = "cwc"


CSS = f"""
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&display=swap');
html, body, [class*="css"], .stApp {{ font-family: 'Inter', 'Segoe UI', sans-serif; }}
.stApp {{ background:
  radial-gradient(1100px 560px at 8% -8%, rgba(76,141,255,.20), transparent 60%),
  radial-gradient(900px 520px at 100% 0%, rgba(34,211,182,.15), transparent 55%),
  radial-gradient(800px 500px at 50% 110%, rgba(255,92,138,.10), transparent 55%), {BG}; }}
.block-container {{ padding-top: 1.4rem; padding-bottom: 3rem; max-width: 1500px; }}
header[data-testid="stHeader"] {{ background: transparent; }}
section[data-testid="stSidebar"] {{ background: linear-gradient(180deg, #0F1A36 0%, #0A0F1E 100%); border-right: 1px solid {BORDER}; }}
section[data-testid="stSidebar"] a {{ border-radius: 10px; }}
h1, h2, h3 {{ letter-spacing: -0.02em; }}
h1 {{ font-weight: 800 !important; }}
[data-testid="stMetric"] {{ background: linear-gradient(145deg, rgba(255,255,255,.06), rgba(255,255,255,.02));
  border: 1px solid rgba(255,255,255,.09); border-radius: 18px; padding: 16px 18px; box-shadow: 0 10px 28px rgba(0,0,0,.28); backdrop-filter: blur(6px); }}
[data-testid="stMetricLabel"] {{ color: {MUTED}; font-weight: 600; text-transform: uppercase; font-size: .72rem; letter-spacing: .06em; }}
[data-testid="stMetricValue"] {{ font-weight: 800; font-size: 1.85rem; background: linear-gradient(90deg,#ffffff,#9fd3ff);
  -webkit-background-clip: text; -webkit-text-fill-color: transparent; }}
.stTabs [data-baseweb="tab-list"] {{ gap: 6px; background: rgba(255,255,255,.04); padding: 6px; border-radius: 14px; border: 1px solid rgba(255,255,255,.06); flex-wrap: wrap; }}
.stTabs [data-baseweb="tab"] {{ border-radius: 10px; padding: 8px 16px; height: auto; color: {MUTED}; font-weight: 600; }}
.stTabs [aria-selected="true"] {{ background: linear-gradient(90deg, {BLUE}, {TEAL}); color: #06101f !important; }}
.stTabs [data-baseweb="tab-highlight"], .stTabs [data-baseweb="tab-border"] {{ display: none; }}
div[data-testid="stPlotlyChart"] {{ border-radius: 18px; background: rgba(255,255,255,.025); border: 1px solid rgba(255,255,255,.07); padding: 6px; box-shadow: 0 8px 22px rgba(0,0,0,.2); }}
div[data-testid="stDataFrame"] {{ border-radius: 14px; overflow: hidden; border: 1px solid rgba(255,255,255,.08); }}
.stButton>button, .stDownloadButton>button {{ border-radius: 12px; border: 1px solid rgba(255,255,255,.12); }}
div[data-baseweb="select"]>div, .stTextInput input, .stNumberInput input {{ border-radius: 12px !important; }}
.hero {{ position: relative; overflow: hidden; border-radius: 26px; padding: 34px 38px; margin-bottom: 18px;
  background: linear-gradient(120deg, rgba(76,141,255,.30), rgba(34,211,182,.22) 55%, rgba(255,176,32,.18));
  border: 1px solid rgba(255,255,255,.12); box-shadow: 0 18px 50px rgba(0,0,0,.35); }}
.hero:after {{ content: "🏏"; position: absolute; right: 30px; top: 6px; font-size: 130px; opacity: .13; transform: rotate(-18deg); }}
.hero h1 {{ margin: 0 0 6px 0; font-size: 2.3rem; line-height: 1.1; }}
.hero p {{ margin: 0; color: #c7d4ee; font-size: 1.02rem; max-width: 900px; }}
.chip {{ display: inline-block; padding: 4px 12px; margin: 12px 8px 0 0; border-radius: 999px; font-size: .78rem; font-weight: 600;
  background: rgba(255,255,255,.10); border: 1px solid rgba(255,255,255,.16); color: #eaf2ff; }}
.card {{ border-radius: 18px; padding: 18px 20px; background: linear-gradient(145deg, rgba(255,255,255,.06), rgba(255,255,255,.02));
  border: 1px solid rgba(255,255,255,.09); box-shadow: 0 10px 28px rgba(0,0,0,.25); height: 100%; }}
.card h4 {{ margin: 0 0 4px 0; color: {MUTED}; font-size: .72rem; text-transform: uppercase; letter-spacing: .07em; }}
.card .big {{ font-size: 1.5rem; font-weight: 800; line-height: 1.15; }}
.card .sub {{ color: {MUTED}; font-size: .85rem; margin-top: 4px; }}
.pill {{ display: inline-block; padding: 2px 10px; border-radius: 999px; font-size: .72rem; font-weight: 700; margin-right: 6px; }}
.section-title {{ font-size: 1.15rem; font-weight: 700; margin: 22px 0 2px 0; }}
.section-sub {{ color: {MUTED}; font-size: .88rem; margin-bottom: 8px; }}
.note {{ border-left: 3px solid {AMBER}; background: rgba(255,176,32,.08); padding: 10px 14px; border-radius: 8px; color: #f3e3c0; font-size: .88rem; }}
hr {{ border-color: rgba(255,255,255,.08); }}
</style>
"""


def inject() -> None:
    register_plotly()
    install_chart_defaults()
    st.markdown(CSS, unsafe_allow_html=True)


def hero(title: str, subtitle: str, chips: list[str] | None = None) -> None:
    chip_html = "".join(f'<span class="chip">{c}</span>' for c in (chips or []))
    st.markdown(
        f'<div class="hero"><h1>{title}</h1><p>{subtitle}</p>{chip_html}</div>',
        unsafe_allow_html=True,
    )


def section(title: str, sub: str = "") -> None:
    st.markdown(
        f'<div class="section-title">{title}</div>'
        + (f'<div class="section-sub">{sub}</div>' if sub else ""),
        unsafe_allow_html=True,
    )


def card(label: str, big: str, sub: str = "", color: str = TEAL) -> str:
    return f'<div class="card" style="border-top:3px solid {color}"><h4>{label}</h4><div class="big">{big}</div><div class="sub">{sub}</div></div>'


def cards(items: list[tuple[str, str, str]], colors: list[str] | None = None) -> None:
    cols = st.columns(len(items))
    palette = colors or [TEAL, BLUE, AMBER, PINK, VIOLET, GREEN]
    for i, (c, (label, big, sub)) in enumerate(zip(cols, items, strict=True)):
        c.markdown(card(label, big, sub, palette[i % len(palette)]), unsafe_allow_html=True)


def pill(text: str, color: str = BLUE) -> str:
    return f'<span class="pill" style="background:{color}33;color:{color};border:1px solid {color}66">{text}</span>'


def note(text: str) -> None:
    st.markdown(f'<div class="note">{text}</div>', unsafe_allow_html=True)


def wrap_title(fig, width: int = 54) -> None:
    """Wrap a long chart title onto two lines so it never runs into the legend or gets cut off."""
    text = getattr(getattr(fig.layout, "title", None), "text", None)
    if not text or "<br>" in text or len(text) <= width:
        return
    words, lines, cur = text.split(" "), [], ""
    for w in words:
        if cur and len(cur) + 1 + len(w) > width and not lines:
            lines.append(cur)
            cur = w
        else:
            cur = f"{cur} {w}".strip()
    lines.append(cur)
    fig.update_layout(title_text="<br>".join(lines))


def install_chart_defaults() -> None:
    """Wrap st.plotly_chart once so every figure gets wrapped titles."""
    if getattr(st.plotly_chart, "_cwc_wrapped", False):
        return
    original = st.plotly_chart

    def plotly_chart(fig, *args, **kwargs):
        try:
            wrap_title(fig)
        except Exception:  # noqa: BLE001 - styling must never break a page
            pass
        return original(fig, *args, **kwargs)

    plotly_chart._cwc_wrapped = True  # type: ignore[attr-defined]
    st.plotly_chart = plotly_chart  # type: ignore[assignment]
