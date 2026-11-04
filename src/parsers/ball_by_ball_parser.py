"""Parse ball-by-ball deliveries from ESPN commentary HTML and Cricsheet JSON.

Never fabricates deliveries. ESPN pages often expose only a recent window of
balls; Cricsheet provides complete innings when a verified match file exists.
"""

from __future__ import annotations

import json
import re
from html import unescape
from typing import Any

from bs4 import BeautifulSoup

from src.utils.logger import get_logger

logger = get_logger(__name__)


def _safe_json(raw: str | None) -> Any | None:
    if not raw:
        return None
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return None


def _strip_html(items: list[dict[str, Any]] | None) -> str | None:
    if not items:
        return None
    parts: list[str] = []
    for item in items:
        html = (item or {}).get("html")
        if not html:
            continue
        text = BeautifulSoup(html, "lxml").get_text(" ", strip=True)
        if text:
            parts.append(unescape(text))
    return " ".join(parts) if parts else None


def _extras_type(ball: dict[str, Any]) -> str | None:
    if ball.get("wides"):
        return "wide"
    if ball.get("noballs"):
        return "noball"
    if ball.get("byes"):
        return "bye"
    if ball.get("legbyes"):
        return "legbye"
    if ball.get("penalties"):
        return "penalty"
    return None


def delivery_from_espn_ball(
    ball: dict[str, Any],
    *,
    match_id: str,
    delivery_sequence: int,
    source_url: str | None = None,
    innings_type: str = "standard",
) -> dict[str, Any]:
    innings_number = int(ball.get("inningNumber") or 0)
    batter_runs = int(ball.get("batsmanRuns") or 0)
    wide = int(ball.get("wides") or 0)
    noball = int(ball.get("noballs") or 0)
    bye = int(ball.get("byes") or 0)
    legbye = int(ball.get("legbyes") or 0)
    penalty = int(ball.get("penalties") or 0)
    extra_runs = wide + noball + bye + legbye + penalty
    total_runs = int(ball.get("totalRuns") if ball.get("totalRuns") is not None else batter_runs + extra_runs)
    is_legal = wide == 0  # wide does not count as legal ball; noball does
    dismissal = ball.get("dismissalText")
    dismissal_type = None
    if isinstance(dismissal, dict):
        dismissal_type = dismissal.get("short") or dismissal.get("long")
    elif isinstance(dismissal, str):
        dismissal_type = dismissal

    return {
        "delivery_id": f"{match_id}_{innings_number}_{delivery_sequence}",
        "match_id": match_id,
        "innings_id": f"{match_id}_{innings_number}",
        "innings_number": innings_number,
        "innings_type": innings_type,
        "over_number": ball.get("overNumber"),
        "ball_number": ball.get("ballNumber"),
        "delivery_sequence": delivery_sequence,
        "legal_ball_number": None,  # filled later if needed
        "batter_id": f"espn_{ball['batsmanPlayerId']}" if ball.get("batsmanPlayerId") else None,
        "non_striker_id": f"espn_{ball['nonStrikerPlayerId']}" if ball.get("nonStrikerPlayerId") else None,
        "bowler_id": f"espn_{ball['bowlerPlayerId']}" if ball.get("bowlerPlayerId") else None,
        "batter_runs": batter_runs,
        "extra_runs": extra_runs,
        "total_runs": total_runs,
        "extras_type": _extras_type(ball),
        "is_wide": wide > 0,
        "is_no_ball": noball > 0,
        "is_bye": bye > 0,
        "is_leg_bye": legbye > 0,
        "is_penalty": penalty > 0,
        "is_wicket": bool(ball.get("isWicket")),
        "dismissal_type": dismissal_type,
        "dismissed_player_id": f"espn_{ball['outPlayerId']}" if ball.get("outPlayerId") else None,
        "fielder_id": None,
        "commentary_text": _strip_html(ball.get("commentTextItems")),
        "is_legal_delivery": is_legal,
        "source_name": "ESPNcricinfo",
        "source_url": source_url,
        "source_ball_id": str(ball.get("id") or ball.get("_uid") or ""),
    }


def parse_espn_commentary_html(
    html: str,
    *,
    match_id: str,
    source_url: str | None = None,
) -> dict[str, Any]:
    """Extract whatever ball comments are embedded in the commentary page."""
    soup = BeautifulSoup(html, "lxml")
    result: dict[str, Any] = {
        "match_id": match_id,
        "source_name": "ESPNcricinfo",
        "source_url": source_url,
        "parse_status": "ok",
        "ball_by_ball_status": "partial",
        "deliveries": [],
        "warnings": [],
    }
    next_data = _safe_json(
        soup.find("script", id="__NEXT_DATA__").string
        if soup.find("script", id="__NEXT_DATA__")
        else None
    )
    if not isinstance(next_data, dict):
        result["parse_status"] = "failed"
        result["ball_by_ball_status"] = "unavailable"
        result["warnings"].append("Missing __NEXT_DATA__")
        return result

    content = ((next_data.get("props") or {}).get("appPageProps") or {}).get("data", {}).get("content") or {}
    balls: list[dict[str, Any]] = []
    recent = content.get("recentBallCommentary") or {}
    for key in ("ballComments", "superOverBallComments"):
        for ball in recent.get(key) or []:
            if isinstance(ball, dict):
                tagged = dict(ball)
                if key == "superOverBallComments":
                    tagged["_innings_type"] = "super_over"
                balls.append(tagged)
    for ball in content.get("comments") or []:
        if isinstance(ball, dict) and ball.get("overNumber") is not None:
            balls.append(ball)

    # Deduplicate by source ball id, preserve chronological order by oversUnique if present
    dedup: dict[str, dict[str, Any]] = {}
    for ball in balls:
        key = str(ball.get("id") or ball.get("_uid") or json.dumps(ball, sort_keys=True, default=str))
        dedup[key] = ball
    ordered = sorted(
        dedup.values(),
        key=lambda b: (
            int(b.get("inningNumber") or 0),
            float(b.get("oversUnique") or b.get("oversActual") or 0),
            int(b.get("ballNumber") or 0),
        ),
    )

    deliveries = []
    for idx, ball in enumerate(ordered, start=1):
        deliveries.append(
            delivery_from_espn_ball(
                ball,
                match_id=match_id,
                delivery_sequence=idx,
                source_url=source_url,
                innings_type=ball.get("_innings_type") or "standard",
            )
        )
    result["deliveries"] = deliveries
    if not deliveries:
        result["ball_by_ball_status"] = "unavailable"
        result["warnings"].append("No ball comments embedded in commentary HTML")
    else:
        result["warnings"].append(
            "ESPNcricinfo commentary HTML typically includes only a recent window of balls; treat as partial unless verified complete."
        )
        result["ball_by_ball_status"] = "partial"
    return result


def _cricsheet_extras(delivery: dict[str, Any]) -> tuple[int, str | None, dict[str, bool]]:
    extras = delivery.get("extras") or {}
    flags = {
        "is_wide": "wides" in extras,
        "is_no_ball": "noballs" in extras,
        "is_bye": "byes" in extras,
        "is_leg_bye": "legbyes" in extras,
        "is_penalty": "penalty" in extras,
    }
    extra_runs = int((delivery.get("runs") or {}).get("extras") or 0)
    extras_type = None
    for key, label in (
        ("wides", "wide"),
        ("noballs", "noball"),
        ("byes", "bye"),
        ("legbyes", "legbye"),
        ("penalty", "penalty"),
    ):
        if key in extras:
            extras_type = label
            break
    return extra_runs, extras_type, flags


def parse_cricsheet_match_json(
    payload: dict[str, Any],
    *,
    match_id: str,
    source_url: str | None = None,
) -> dict[str, Any]:
    """Convert a Cricsheet match JSON document into delivery records."""
    result: dict[str, Any] = {
        "match_id": match_id,
        "source_name": "Cricsheet",
        "source_url": source_url,
        "parse_status": "ok",
        "ball_by_ball_status": "complete",
        "deliveries": [],
        "info": payload.get("info") or {},
        "warnings": [],
    }
    deliveries: list[dict[str, Any]] = []
    seq_by_innings: dict[int, int] = {}

    for innings_idx, innings in enumerate(payload.get("innings") or [], start=1):
        if not isinstance(innings, dict):
            continue
        innings_number = innings_idx
        innings_type = "super_over" if innings.get("super_over") else "standard"
        for over in innings.get("overs") or []:
            over_number = int(over.get("over", 0)) + 1  # Cricsheet is 0-based
            for ball_idx, delivery in enumerate(over.get("deliveries") or [], start=1):
                seq_by_innings[innings_number] = seq_by_innings.get(innings_number, 0) + 1
                delivery_sequence = seq_by_innings[innings_number]
                runs = delivery.get("runs") or {}
                batter_runs = int(runs.get("batter") or 0)
                extra_runs, extras_type, flags = _cricsheet_extras(delivery)
                total_runs = int(runs.get("total") if runs.get("total") is not None else batter_runs + extra_runs)
                wickets = delivery.get("wickets") or []
                dismissed = None
                dismissal_type = None
                fielder_id = None
                if wickets:
                    dismissed = wickets[0].get("player_out")
                    dismissal_type = wickets[0].get("kind")
                    fielders = wickets[0].get("fielders") or []
                    if fielders and isinstance(fielders[0], dict):
                        fielder_id = fielders[0].get("name")

                deliveries.append(
                    {
                        "delivery_id": f"{match_id}_{innings_number}_{delivery_sequence}",
                        "match_id": match_id,
                        "innings_id": f"{match_id}_{innings_number}",
                        "innings_number": innings_number,
                        "innings_type": innings_type,
                        "over_number": over_number,
                        "ball_number": ball_idx,
                        "delivery_sequence": delivery_sequence,
                        "legal_ball_number": None,
                        "batter_id": delivery.get("batter"),
                        "non_striker_id": delivery.get("non_striker"),
                        "bowler_id": delivery.get("bowler"),
                        "batter_runs": batter_runs,
                        "extra_runs": extra_runs,
                        "total_runs": total_runs,
                        "extras_type": extras_type,
                        "is_wide": flags["is_wide"],
                        "is_no_ball": flags["is_no_ball"],
                        "is_bye": flags["is_bye"],
                        "is_leg_bye": flags["is_leg_bye"],
                        "is_penalty": flags["is_penalty"],
                        "is_wicket": bool(wickets),
                        "dismissal_type": dismissal_type,
                        "dismissed_player_id": dismissed,
                        "fielder_id": fielder_id,
                        "commentary_text": None,
                        "is_legal_delivery": not flags["is_wide"],
                        "source_name": "Cricsheet",
                        "source_url": source_url,
                        "source_ball_id": f"{innings_number}.{over.get('over')}.{ball_idx}",
                    }
                )

    result["deliveries"] = deliveries
    if not deliveries:
        result["ball_by_ball_status"] = "unavailable"
        result["parse_status"] = "partial"
        result["warnings"].append("Cricsheet file contained no deliveries")
    return result


def normalize_team_name(name: str | None) -> str:
    if not name:
        return ""
    cleaned = name.strip().lower()
    cleaned = cleaned.replace("&", "and")
    cleaned = re.sub(r"[^a-z0-9]+", " ", cleaned)
    return re.sub(r"\s+", " ", cleaned).strip()
