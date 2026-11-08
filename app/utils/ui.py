# ruff: noqa: E501
"""Shared page setup (theme, hero banner) and small UI helpers."""

from __future__ import annotations

import sys
from pathlib import Path

import streamlit as st

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.utils import theme  # noqa: E402
from app.utils.theme import FORMAT_COLORS  # noqa: E402,F401  (re-exported for the pages)


def setup(title: str, icon: str = "🏏", subtitle: str = "", chips: list[str] | None = None) -> bool:
    """Configure the page, apply the theme and draw the hero banner.

    Returns False (after showing a message) if the gold database is missing."""
    try:
        st.set_page_config(
            page_title=f"{title} - CricketWorldCup Analytics", page_icon=icon, layout="wide"
        )
    except st.errors.StreamlitAPIException:
        pass  # already configured (multipage re-run)
    theme.inject()
    from app.utils.database import DB_PATH, db_available

    theme.hero(f"{icon} {title}", subtitle or "Men's ICC ODI and T20 World Cups", chips)
    if not db_available():
        st.error(
            f"Gold database not found at `{DB_PATH}`. Run `python scripts/load_warehouse.py` first."
        )
        return False
    return True


def synthetic_banner() -> None:
    st.warning(
        "**SYNTHETIC DEMO DATA** - pitch, weather and day/night values below are random placeholders, "
        "not real observations. Do not draw cricket conclusions from them.",
        icon="⚠️",
    )


def coverage_note() -> None:
    from app.utils import database

    if database.competition() == "wc":
        st.caption(
            "Ball-by-ball detail exists for about 85% of played matches; the rest are scorecard-only "
            "(see Data Engineering > Coverage). ODI data starts at the 1999 World Cup (scorecards only until 2003)."
        )
        return
    try:
        from app.utils.database import run

        c = run(
            "select count(*) n, count(*) filter (where has_ball_by_ball) bbb from gold.fact_matches"
        ).iloc[0]
        text = (
            f"{int(c['n'])} matches; ball-by-ball (Cricsheet) for {int(c['bbb'])}. The others are scorecard-only "
            "from ESPNcricinfo (abandoned and no-result matches, and editions older than the open ball-by-ball data)."
        )
        if database.competition() == "wtc":
            text += (
                " Each edition is a two-year cycle; 5 matches of 2019-21 were postponed and never played, "
                "and the 2025-27 cycle is still in progress."
            )
        st.caption(text)
    except Exception:  # noqa: BLE001 - a caption must never break a page
        st.caption("Sources: Cricsheet ball-by-ball files and ESPNcricinfo scorecards.")
