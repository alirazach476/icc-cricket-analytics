"""Parse ESPNcricinfo series schedule HTML into match discovery records."""

from __future__ import annotations

import json
import re
from typing import Any

from bs4 import BeautifulSoup

from src.utils.logger import get_logger

logger = get_logger(__name__)

BASE = "https://www.espncricinfo.com"


def _safe_json_loads(raw: str | None) -> Any | None:
    if not raw:
        return None
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return None


def map_match_stage(title: str | None, final_type: int | None = None) -> str:
    """Normalize a source match title into a supported stage label.

    Uses source title text (not a fixed tournament bracket assumption).
    """
    text = (title or "").strip()
    lower = text.lower()

    if "third place" in lower or "3rd place" in lower:
        return "Third Place"
    if "semi" in lower:
        return "Semifinal"
    if "super eight" in lower or "super 8" in lower or "super8" in lower:
        return "Super Eight"
    if "super six" in lower or "super 6" in lower:
        return "Super Six"
    if re.fullmatch(r"final", lower) or lower.endswith(" final") and "semi" not in lower:
        if "quarter" not in lower and "semi" not in lower:
            return "Final"
    if final_type == 1 and "semi" not in lower:
        return "Final"
    if final_type == 3:
        return "Semifinal"
    if re.search(r"\bmatch\b", lower) or "group" in lower:
        return "Group Stage"
    if text:
        return "Other"
    return "Other"


def _team_side(entry: dict[str, Any] | None) -> dict[str, Any] | None:
    if not isinstance(entry, dict):
        return None
    team = entry.get("team") or {}
    if not isinstance(team, dict) or not team.get("objectId"):
        return None
    return {
        "team_id": f"espn_{team.get('objectId')}",
        "source_team_id": str(team.get("objectId")),
        "team_name": team.get("longName") or team.get("name"),
        "abbreviation": team.get("abbreviation"),
        "is_home": entry.get("isHome"),
    }


def build_match_urls(series: dict[str, Any], match: dict[str, Any]) -> dict[str, str]:
    series_slug = series.get("slug")
    series_oid = series.get("objectId")
    match_slug = match.get("slug")
    match_oid = match.get("objectId")
    if not all([series_slug, series_oid, match_slug, match_oid]):
        return {}
    base_path = f"/series/{series_slug}-{series_oid}/{match_slug}-{match_oid}"
    return {
        "source_url": f"{BASE}{base_path}",
        "scorecard_url": f"{BASE}{base_path}/full-scorecard",
        "commentary_url": f"{BASE}{base_path}/ball-by-ball-commentary",
    }


def match_record_from_espn(
    match: dict[str, Any],
    *,
    tournament_id: str,
) -> dict[str, Any] | None:
    """Convert one ESPN match object into a discovery record."""
    object_id = match.get("objectId")
    if object_id is None:
        return None

    series = match.get("series") or {}
    teams = match.get("teams") or []
    team1 = _team_side(teams[0]) if len(teams) > 0 else None
    team2 = _team_side(teams[1]) if len(teams) > 1 else None
    urls = build_match_urls(series, match)
    ground = match.get("ground") or {}
    town = ground.get("town") if isinstance(ground.get("town"), dict) else {}

    title = match.get("title")
    stage = map_match_stage(title, match.get("finalType"))

    match_number = None
    if isinstance(title, str):
        found = re.match(r"(\d+)(?:st|nd|rd|th)?\s+Match", title, flags=re.I)
        if found:
            match_number = int(found.group(1))

    start_date = match.get("startDate")
    return {
        "match_id": str(object_id),
        "tournament_id": tournament_id,
        "source_match_id": str(object_id),
        "match_number": match_number,
        "match_stage": stage,
        "match_type": title,
        "match_date": str(start_date)[:10] if start_date else None,
        "start_time": match.get("startTime"),
        "venue": ground.get("name") or ground.get("longName"),
        "city": town.get("name") or ground.get("smallName") or ground.get("location"),
        "team1_id": (team1 or {}).get("team_id"),
        "team2_id": (team2 or {}).get("team_id"),
        "team1_name": (team1 or {}).get("team_name"),
        "team2_name": (team2 or {}).get("team_name"),
        "toss_winner_id": None,
        "toss_decision": None,
        "winner_id": f"espn_{match['winnerTeamId']}" if match.get("winnerTeamId") else None,
        "result_type": match.get("status"),
        "result_margin": match.get("statusText"),
        "player_of_match_id": None,
        "umpires": None,
        "match_referee": None,
        "is_cancelled": bool(match.get("isCancelled")),
        "is_super_over": bool(match.get("isSuperOver")),
        "has_scorecard": bool(match.get("hasScorecard")),
        "has_commentary": bool(match.get("hasCommentary")),
        "source_url": urls.get("source_url"),
        "scorecard_url": urls.get("scorecard_url"),
        "commentary_url": urls.get("commentary_url"),
        "discovery_status": "discovered",
        "source_name": "ESPNcricinfo",
        "source_title": title,
    }


def extract_matches_from_next_data(
    next_data: dict[str, Any],
    *,
    tournament_id: str,
) -> list[dict[str, Any]]:
    """Extract match list from schedule (preferred) or series homepage payload."""
    props = next_data.get("props") or {}
    app = props.get("appPageProps") or {}
    data = app.get("data") if isinstance(app, dict) else None
    content = data.get("content") if isinstance(data, dict) else None
    if not isinstance(content, dict):
        return []

    raw_matches: list[dict[str, Any]] = []
    if isinstance(content.get("matches"), list):
        raw_matches = [m for m in content["matches"] if isinstance(m, dict)]
    elif isinstance(content.get("recentResults"), list):
        # Partial fallback — series homepage often has only recent results
        raw_matches = [m for m in content["recentResults"] if isinstance(m, dict)]
        logger.warning(
            "%s: using recentResults fallback (%s matches); schedule page preferred",
            tournament_id,
            len(raw_matches),
        )

    records: list[dict[str, Any]] = []
    seen: set[str] = set()
    for match in raw_matches:
        record = match_record_from_espn(match, tournament_id=tournament_id)
        if not record:
            continue
        if record["match_id"] in seen:
            continue
        seen.add(record["match_id"])
        records.append(record)
    return records


def parse_match_schedule_html(
    html: str,
    *,
    tournament_id: str,
    source_url: str | None = None,
) -> dict[str, Any]:
    """Parse a schedule or series HTML document into discovered matches."""
    soup = BeautifulSoup(html, "lxml")
    result: dict[str, Any] = {
        "tournament_id": tournament_id,
        "source_url": source_url,
        "parse_status": "ok",
        "matches": [],
        "warnings": [],
    }

    next_tag = soup.find("script", id="__NEXT_DATA__")
    next_data = _safe_json_loads(next_tag.string if next_tag else None)
    if not isinstance(next_data, dict):
        result["parse_status"] = "failed"
        result["warnings"].append("Missing or invalid __NEXT_DATA__")
        return result

    matches = extract_matches_from_next_data(next_data, tournament_id=tournament_id)
    result["matches"] = matches
    if not matches:
        result["parse_status"] = "partial"
        result["warnings"].append("No matches found in page payload")
    return result
