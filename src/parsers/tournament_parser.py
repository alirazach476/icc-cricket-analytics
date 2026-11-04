"""Parse ESPNcricinfo tournament / series HTML into structured metadata.

Extracts fields present in the page only. Does not invent match counts.
"""

from __future__ import annotations

import json
import re
from typing import Any

from bs4 import BeautifulSoup

from src.utils.logger import get_logger

logger = get_logger(__name__)


def _safe_json_loads(raw: str | None) -> Any | None:
    if not raw:
        return None
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return None


def _clean_title(value: str | None) -> str | None:
    if not value:
        return None
    cleaned = re.split(
        r"\s+\||\s+Fixtures|\s+Live Score|\s+Schedule|\s+Points Table",
        value,
        maxsplit=1,
    )[0].strip()
    return cleaned or value.strip()


def _extract_series_object(next_data: dict[str, Any]) -> dict[str, Any] | None:
    """Locate the series object in current ESPNcricinfo Next.js payloads."""
    props = next_data.get("props") or {}
    # Current layout (observed 2026): props.appPageProps.data.series
    app_page = props.get("appPageProps") or {}
    data = app_page.get("data") if isinstance(app_page, dict) else None
    if isinstance(data, dict) and isinstance(data.get("series"), dict):
        return data["series"]

    # Older / alternate layouts
    page_props = props.get("pageProps") or {}
    if isinstance(page_props, dict):
        if isinstance(page_props.get("series"), dict):
            return page_props["series"]
        nested = page_props.get("data")
        if isinstance(nested, dict) and isinstance(nested.get("series"), dict):
            return nested["series"]
    return None


def parse_tournament_html(html: str, *, source_url: str | None = None) -> dict[str, Any]:
    """Extract tournament-level fields from series HTML."""
    soup = BeautifulSoup(html, "lxml")
    result: dict[str, Any] = {
        "source_url": source_url,
        "parse_status": "ok",
        "page_title": None,
        "og_title": None,
        "discovered_name": None,
        "json_ld": [],
        "next_data_found": False,
        "series_object": None,
        "query": None,
        "extracted_fields": {},
        "warnings": [],
    }

    if soup.title:
        result["page_title"] = soup.title.get_text(strip=True)

    og = soup.find("meta", property="og:title")
    if og and og.get("content"):
        result["og_title"] = og["content"].strip()

    for tag in soup.find_all("script", attrs={"type": "application/ld+json"}):
        payload = _safe_json_loads(tag.string or tag.get_text())
        if payload is not None:
            result["json_ld"].append(payload)

    next_tag = soup.find("script", id="__NEXT_DATA__")
    next_data = None
    if next_tag and (next_tag.string or next_tag.get_text()):
        next_data = _safe_json_loads(next_tag.string or next_tag.get_text())
        result["next_data_found"] = next_data is not None

    extracted: dict[str, Any] = {}

    if isinstance(next_data, dict):
        result["query"] = next_data.get("query")
        series = _extract_series_object(next_data)
        if series:
            result["series_object"] = {
                key: series.get(key)
                for key in [
                    "id",
                    "objectId",
                    "slug",
                    "name",
                    "longName",
                    "seoName",
                    "alternateName",
                    "year",
                    "season",
                    "startDate",
                    "endDate",
                    "description",
                    "totalTeams",
                    "totalSquads",
                    "hasStandings",
                    "matchClass",
                    "trophy",
                ]
                if key in series
            }
            extracted["source_series_object_id"] = series.get("objectId")
            extracted["source_series_id"] = series.get("id")
            extracted["slug"] = series.get("slug")
            extracted["name"] = series.get("seoName") or series.get("longName") or series.get("name")
            extracted["alternate_name"] = series.get("alternateName")
            if series.get("startDate"):
                extracted["start_date"] = str(series["startDate"])[:10]
            if series.get("endDate"):
                extracted["end_date"] = str(series["endDate"])[:10]
            if series.get("season") is not None:
                extracted["season"] = series.get("season")
            if series.get("year") is not None:
                extracted["year"] = series.get("year")
            if series.get("totalTeams") is not None:
                extracted["number_of_teams"] = series.get("totalTeams")
            if series.get("description"):
                extracted["host_description"] = series.get("description")
            match_class = series.get("matchClass") or {}
            if isinstance(match_class, dict) and match_class.get("name"):
                extracted["match_class_name"] = match_class["name"]

    # JSON-LD name only as fallback (do not deep-search unrelated "name" fields)
    if not extracted.get("name"):
        for item in result["json_ld"]:
            if isinstance(item, dict) and item.get("name"):
                extracted["json_ld_name"] = item["name"]
                break

    discovered = (
        extracted.get("name")
        or extracted.get("json_ld_name")
        or _clean_title(result.get("og_title"))
        or _clean_title(result.get("page_title"))
    )
    result["discovered_name"] = discovered
    result["extracted_fields"] = extracted

    if not result["discovered_name"]:
        result["parse_status"] = "partial"
        result["warnings"].append("Could not determine tournament name from page")
        logger.warning("Tournament HTML parse partial for %s", source_url)
    elif not result.get("series_object"):
        result["parse_status"] = "partial"
        result["warnings"].append("Series object missing; used title/meta fallback")

    return result
