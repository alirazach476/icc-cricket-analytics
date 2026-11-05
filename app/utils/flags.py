# ruff: noqa: E501
"""Team name -> flag asset code.

Flags are local SVG files (web/public/flags, from the MIT-licensed `flag-icons` set), so they render the same on every
operating system and need no internet. Emoji flags are not used (Windows shows letter pairs instead).

West Indies is a multi-nation team with no national flag: ``wi-crest.svg`` is the West Indies cricket flag (maroon with the
crest, supplied by the project owner). Teams not yet known (World Cup 2027 qualifier slots) return
None and the UI draws a neutral initials badge instead of a wrong flag.
"""

from __future__ import annotations

# canonical team name (as stored in the gold layer) -> flag-icons code
FLAG_CODES: dict[str, str] = {
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
    "West Indies": "wi-crest",
    "United Arab Emirates": "ae",
    "United States of America": "us",
    "Zimbabwe": "zw",
}

# spelling variants seen in ESPNcricinfo / Cricsheet / ICC material
ALIASES: dict[str, str] = {
    "usa": "United States of America",
    "u.s.a.": "United States of America",
    "us": "United States of America",
    "united states": "United States of America",
    "uae": "United Arab Emirates",
    "u.a.e.": "United Arab Emirates",
    "png": "Papua New Guinea",
    "ned": "Netherlands",
    "holland": "Netherlands",
    "nz": "New Zealand",
    "sa": "South Africa",
    "rsa": "South Africa",
    "sl": "Sri Lanka",
    "ind": "India",
    "aus": "Australia",
    "eng": "England",
    "pak": "Pakistan",
    "ban": "Bangladesh",
    "afg": "Afghanistan",
    "zim": "Zimbabwe",
    "ire": "Ireland",
    "sco": "Scotland",
    "nam": "Namibia",
    "ken": "Kenya",
    "can": "Canada",
    "ber": "Bermuda",
    "hk": "Hong Kong",
    "windies": "West Indies",
    "wi": "West Indies",
    "hong kong, china": "Hong Kong",
}


def canonical(team: str | None) -> str | None:
    """Canonical team name for any known spelling (None when the team has no flag)."""
    if not team:
        return None
    t = str(team).strip()
    if t in FLAG_CODES:
        return t
    low = t.lower()
    for name in FLAG_CODES:
        if name.lower() == low:
            return name
    return ALIASES.get(low)


def flag_code(team: str | None) -> str | None:
    c = canonical(team)
    return FLAG_CODES.get(c) if c else None


def flag_map() -> dict[str, str]:
    """Every accepted spelling (lower case) -> code, sent to the browser once."""
    out = {n.lower(): c for n, c in FLAG_CODES.items()}
    for a, n in ALIASES.items():
        out[a] = FLAG_CODES[n]
    return out
