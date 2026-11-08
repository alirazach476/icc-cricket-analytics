# ruff: noqa: E501
"""World Cup editions: logo files and a colour theme taken from each logo."""

from __future__ import annotations

# chart order = the slots of the base chart palette: BLUE, AMBER, TEAL, PINK, VIOLET, GREEN, CYAN, RED
DEFAULT_CHART = [
    "#4C8DFF",
    "#FFB020",
    "#22D3B6",
    "#FF5C8A",
    "#9B7BFF",
    "#6BDB6B",
    "#38E1FF",
    "#FF6B6B",
]
BASE_SLOTS = (
    DEFAULT_CHART  # hex codes the Python charts use; the client swaps them for the edition palette
)

DEFAULT_THEME = {
    "bg": "#0A0F1E",
    "panel": "#111A2E",
    "primary": "#22D3B6",
    "secondary": "#4C8DFF",
    "tertiary": "#FFB020",
    "chart": DEFAULT_CHART,
}

# (primary, secondary, tertiary, background, 8 chart colours)
_P = {
    "wc27-2027": (
        "#FDB913",
        "#2072D0",
        "#EC2049",
        "#1C070B",
        ["#2072D0", "#FDB913", "#049A52", "#EC2049", "#C98504", "#6BDB9B", "#5CC8F2", "#FF6B6B"],
    ),
    "ct-2002": (
        "#3D8BE0",
        "#F5C518",
        "#E03A3E",
        "#07142B",
        ["#3D8BE0", "#F5C518", "#2FB67C", "#E03A3E", "#9B7BFF", "#6BDB6B", "#5CC8F2", "#FF6B6B"],
    ),
    "ct-2004": (
        "#3E86E0",
        "#F2C230",
        "#E63946",
        "#071530",
        ["#3E86E0", "#F2C230", "#2FB67C", "#E63946", "#9B7BFF", "#6BDB6B", "#5CC8F2", "#FF6B6B"],
    ),
    "ct-2006": (
        "#F08A1C",
        "#2D78D0",
        "#2FA84F",
        "#06142E",
        ["#2D78D0", "#F08A1C", "#2FA84F", "#E0383A", "#9B7BFF", "#6BDB6B", "#5CC8F2", "#FF6B6B"],
    ),
    "ct-2009": (
        "#E8B21F",
        "#B9BCC2",
        "#F7DC6F",
        "#0B0B0D",
        ["#E8B21F", "#B9BCC2", "#6FD3C0", "#F08A5D", "#9B7BFF", "#8FD36B", "#7CCBF2", "#E05A5A"],
    ),
    "ct-2013": (
        "#F0A81A",
        "#A8ACB3",
        "#FFD66B",
        "#111214",
        ["#F0A81A", "#A8ACB3", "#6FD3C0", "#F08A5D", "#9B7BFF", "#8FD36B", "#7CCBF2", "#E05A5A"],
    ),
    "ct-2017": (
        "#C9A36B",
        "#B8BCC4",
        "#E6C99A",
        "#0B1B3D",
        ["#C9A36B", "#6FA3E0", "#B8BCC4", "#E6C99A", "#9B7BFF", "#6BDB9B", "#5CC8F2", "#E07A6A"],
    ),
    "ct-2025": (
        "#3CF03C",
        "#4C6BFF",
        "#B6FF4D",
        "#0B1578",
        ["#4C6BFF", "#3CF03C", "#FFD93D", "#FF5C8A", "#9B7BFF", "#B6FF4D", "#38E1FF", "#FF6B6B"],
    ),
    "wtc-2021": (
        "#CFC3B0",
        "#9AA0A6",
        "#E8DCC4",
        "#0B0B0C",
        ["#9AB4D8", "#CFC3B0", "#6FD3C0", "#E07A6A", "#9B7BFF", "#8FD36B", "#7CCBF2", "#E05A5A"],
    ),
    "wtc-2023": (
        "#BFC5C9",
        "#9AA0A6",
        "#D8C7A8",
        "#0A0B0D",
        ["#9AB4D8", "#D8C7A8", "#6FD3C0", "#E07A6A", "#9B7BFF", "#8FD36B", "#7CCBF2", "#E05A5A"],
    ),
    "wtc-2025": (
        "#D8C7A8",
        "#A8AEB3",
        "#EEE2CC",
        "#0C0C0E",
        ["#9AB4D8", "#D8C7A8", "#6FD3C0", "#E07A6A", "#9B7BFF", "#8FD36B", "#7CCBF2", "#E05A5A"],
    ),
    "odi-1999": (
        "#E5342D",
        "#2A5DB0",
        "#D4A82A",
        "#0D1022",
        ["#E5342D", "#2A5DB0", "#D4A82A", "#2FB67C", "#9B7BFF", "#6BDB6B", "#5CC8F2", "#FF8A5C"],
    ),
    "odi-2003": (
        "#F2B632",
        "#FFFFFF",
        "#9AA0A6",
        "#0B0B0D",
        ["#F2B632", "#FFFFFF", "#C9A24B", "#E7E7E7", "#8D8D8D", "#D9822B", "#F7DC8A", "#B5463A"],
    ),
    "odi-2007": (
        "#29B6F0",
        "#7AC943",
        "#F8B012",
        "#071426",
        ["#29B6F0", "#F8B012", "#7AC943", "#E8262B", "#8E7CFF", "#4CD08A", "#6FD8FF", "#FF6A4D"],
    ),
    "odi-2011": (
        "#F7931E",
        "#E8304F",
        "#7AC143",
        "#160B14",
        ["#2E9BE0", "#F7931E", "#7AC143", "#E8304F", "#B05CE0", "#9AD45A", "#4CC3E8", "#FF5A5F"],
    ),
    "odi-2015": (
        "#2BA3D8",
        "#E8622C",
        "#6BB33F",
        "#08143A",
        ["#3E7BE0", "#F08A3C", "#6BB33F", "#E8622C", "#7C6FE0", "#8ED36A", "#2BC4E8", "#FF6B6B"],
    ),
    "odi-2019": (
        "#FF4A7D",
        "#8FA7BC",
        "#4C8DFF",
        "#101B2B",
        ["#6FA3D8", "#FF4A7D", "#8FA7BC", "#FF8FB0", "#9B7BFF", "#6BDB9B", "#3EC8E8", "#FF6B6B"],
    ),
    "odi-2023": (
        "#FF2BAE",
        "#FFD400",
        "#1AA3DC",
        "#12053A",
        ["#1AA3DC", "#FFD400", "#B07CFF", "#FF2BAE", "#8B5CFF", "#59E0A0", "#52D6FF", "#FF6B6B"],
    ),
    "t20-2007": (
        "#E3173E",
        "#00A651",
        "#FDBB11",
        "#0B0C10",
        ["#2E86E8", "#FDBB11", "#00A651", "#E3173E", "#9B7BFF", "#6BDB6B", "#38E1FF", "#FF6B6B"],
    ),
    "t20-2009": (
        "#F59B1B",
        "#E8321E",
        "#2F86E0",
        "#140A0A",
        ["#2F86E0", "#F59B1B", "#47C0A8", "#E8321E", "#9B7BFF", "#7CD96B", "#4FD0F0", "#FF6B5A"],
    ),
    "t20-2010": (
        "#2BB4D8",
        "#F58220",
        "#C2415F",
        "#0A1A22",
        ["#2BB4D8", "#F58220", "#47C58F", "#C2415F", "#9B7BFF", "#8AD65F", "#6FE0F5", "#FF6B6B"],
    ),
    "t20-2012": (
        "#F7A81B",
        "#E1261C",
        "#0B8AD8",
        "#0A1220",
        ["#2B9AE8", "#F7A81B", "#3FC58F", "#E1261C", "#9B7BFF", "#7CD96B", "#4FD0F0", "#FF7A5A"],
    ),
    "t20-2014": (
        "#2DB34A",
        "#F58220",
        "#1D8FD8",
        "#07160F",
        ["#2E9BE8", "#F58220", "#2DB34A", "#E8488A", "#9B7BFF", "#8ADB5F", "#4FD0F0", "#FF6B6B"],
    ),
    "t20-2016": (
        "#E8228A",
        "#F2542D",
        "#8B6CFF",
        "#150C3A",
        ["#8B6CFF", "#F2542D", "#2BC4E8", "#E8228A", "#B07CFF", "#59E0A0", "#52D6FF", "#FF6B6B"],
    ),
    "t20-2021": (
        "#8E6DFF",
        "#FF3158",
        "#B28CFF",
        "#10063A",
        ["#8E6DFF", "#FFB020", "#2BD4C4", "#FF3158", "#B28CFF", "#6BDB9B", "#38E1FF", "#FF6B6B"],
    ),
    "t20-2022": (
        "#00A5DE",
        "#E81E5F",
        "#FFD400",
        "#0E0A33",
        ["#00A5DE", "#FFD400", "#2BD4C4", "#E81E5F", "#9B7BFF", "#6BDB9B", "#6FE0F5", "#FF6B6B"],
    ),
    "t20-2024": (
        "#FF1B8D",
        "#6F5BFF",
        "#00D1FF",
        "#0C0640",
        ["#6F5BFF", "#FFC400", "#00D1FF", "#FF1B8D", "#B07CFF", "#59E0A0", "#52D6FF", "#FF6B6B"],
    ),
    "t20-2026": (
        "#FB9102",
        "#7A6BFF",
        "#FFD166",
        "#0F0636",
        ["#7A6BFF", "#FB9102", "#2BD4C4", "#FFB84D", "#B07CFF", "#6BDB6B", "#38E1FF", "#FF6B6B"],
    ),
}
# Champions Trophy and World Test Championship: one palette per competition (no per-edition logos supplied)
COMPETITION_THEMES = {
    "ct": (
        "#F5B82E",
        "#2D8CFF",
        "#38E1FF",
        "#06122B",
        ["#2D8CFF", "#F5B82E", "#22D3B6", "#FF5C8A", "#9B7BFF", "#6BDB6B", "#38E1FF", "#FF6B6B"],
    ),
    "wtc": (
        "#E6B450",
        "#8E7CFF",
        "#38E1FF",
        "#0B0A1F",
        ["#8E7CFF", "#E6B450", "#22D3B6", "#FF5C8A", "#4C8DFF", "#6BDB6B", "#38E1FF", "#FF6B6B"],
    ),
}
COMPETITIONS = {
    "wc27": {
        "name": "World Cup 2027",
        "long": "ICC Men's Cricket World Cup 2027 (upcoming)",
        "kicker": "ICC Men's Cricket World Cup",
        "note": "upcoming",
    },
    "wc": {"name": "World Cups", "long": "ICC Men's Cricket & T20 World Cups", "kicker": None},
    "ct": {
        "name": "Champions Trophy",
        "long": "ICC Champions Trophy",
        "kicker": "ICC Champions Trophy",
    },
    "wtc": {
        "name": "Test Championship",
        "long": "ICC World Test Championship (finals)",
        "kicker": "ICC World Test Championship Final",
    },
}
BANNERS = {
    "wc27-2027": "banner-wc27-2027.jpg",
    "ct-2009": "banner-ct-2009.jpg",
    "ct-2017": "banner-ct-2017.jpg",
    "ct-2025": "banner-ct-2025.jpg",
    "wtc-2021": "banner-wtc-2021.jpg",
    "wtc-2023": "banner-wtc-2023.jpg",
    "odi-2011": "banner-odi-2011.jpg",
    "odi-2015": "banner-odi-2015.jpg",
    "odi-2019": "banner-odi-2019.jpg",
    "odi-2023": "banner-odi-2023.jpg",
    "t20-2007": "banner-t20-2007.jpg",
    "t20-2012": "banner-t20-2012.jpg",
    "t20-2014": "banner-t20-2014.jpg",
    "t20-2016": "banner-t20-2016.jpg",
    "t20-2021": "banner-t20-2021.jpg",
    "t20-2022": "banner-t20-2022.jpg",
    "t20-2024": "banner-t20-2024.jpg",
    "t20-2026": "banner-t20-2026.jpg",
    "ct-2013": "banner-ct-2013.png",
}


def edition_id(fmt: str, year: int) -> str:
    return f"{fmt.lower()}-{int(year)}"


def theme_for(eid: str) -> dict:
    code = eid.split("-")[0]
    if eid not in _P and code in COMPETITION_THEMES:
        primary, secondary, tertiary, bg, chart = COMPETITION_THEMES[code]
        return {
            "bg": bg,
            "panel": "#ffffff0d",
            "primary": primary,
            "secondary": secondary,
            "tertiary": tertiary,
            "chart": chart,
        }
    if eid not in _P:
        return DEFAULT_THEME
    primary, secondary, tertiary, bg, chart = _P[eid]
    return {
        "bg": bg,
        "panel": "#ffffff0d",
        "primary": primary,
        "secondary": secondary,
        "tertiary": tertiary,
        "chart": chart,
    }


def logo_for(eid: str) -> str:
    """The edition's own logo if one was dropped into web/public/logos, else the ICC logo."""
    from pathlib import Path

    import json

    here = Path(__file__).resolve().parent
    public = here.parents[0] / "web" / "public"
    # serverless bundles drop public/ folders: the deploy step ships the list of logo files instead
    listed = here / "logo_files.json"
    names = set(json.loads(listed.read_text())) if listed.exists() else None
    ok = f"{eid}.png" in names if names is not None else (public / "logos" / f"{eid}.png").exists()
    return f"/logos/{eid}.png" if ok else "/icc-logo.png"


def banner_for(eid: str) -> str | None:
    return f"/logos/{BANNERS[eid]}" if eid in BANNERS else None
