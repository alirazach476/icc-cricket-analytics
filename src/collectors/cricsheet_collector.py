"""Download and index Cricsheet World Cup JSON as a supplementary BBB source.

Respects cricsheet.org robots.txt (downloads/ allowed; /data/ disallowed).
"""

from __future__ import annotations

import json
import zipfile
from pathlib import Path
from typing import Any

import requests

from src.parsers.ball_by_ball_parser import normalize_team_name, parse_cricsheet_match_json
from src.utils.config import get_project_root, get_settings
from src.utils.helpers import ensure_dir, utc_now_iso
from src.utils.logger import get_logger

logger = get_logger(__name__)

CRICSHEET_DOWNLOADS = {
    "ODI": "https://cricsheet.org/downloads/icc_mens_cricket_world_cup_male_json.zip",
    "T20": "https://cricsheet.org/downloads/icc_mens_t20_world_cup_male_json.zip",
}


class CricsheetCollector:
    def __init__(self) -> None:
        settings = get_settings()
        collection = settings.get("collection", {})
        self.user_agent = collection.get(
            "user_agent",
            "CricketWorldCupAnalytics/0.1 (educational research; local use)",
        )
        self.timeout = float(collection.get("timeout_seconds", 60))
        self.project_root = get_project_root()
        self.base_dir = ensure_dir(self.project_root / "data" / "raw" / "commentary" / "cricsheet")
        self._index_cache: dict[str, list[dict[str, Any]]] = {}

    def download_bundle(self, match_format: str, *, force: bool = False) -> Path:
        match_format = match_format.upper()
        if match_format not in CRICSHEET_DOWNLOADS:
            raise ValueError(f"Unsupported format for Cricsheet WC bundle: {match_format}")
        url = CRICSHEET_DOWNLOADS[match_format]
        zip_path = self.base_dir / f"icc_mens_{match_format.lower()}_world_cup_male_json.zip"
        extract_dir = ensure_dir(self.base_dir / match_format.lower())

        if zip_path.exists() and not force:
            logger.info("Using cached Cricsheet zip: %s", zip_path)
        else:
            logger.info("Downloading Cricsheet bundle: %s", url)
            response = requests.get(
                url,
                headers={"User-Agent": self.user_agent},
                timeout=self.timeout,
            )
            response.raise_for_status()
            zip_path.write_bytes(response.content)
            meta = {
                "source_name": "Cricsheet",
                "source_url": url,
                "downloaded_at": utc_now_iso(),
                "bytes": len(response.content),
            }
            zip_path.with_suffix(zip_path.suffix + ".meta.json").write_text(
                json.dumps(meta, indent=2), encoding="utf-8"
            )

        # Extract if empty or force
        json_files = list(extract_dir.glob("*.json"))
        if force or not json_files:
            with zipfile.ZipFile(zip_path, "r") as zf:
                zf.extractall(extract_dir)
            logger.info("Extracted %s JSON files to %s", len(list(extract_dir.glob('*.json'))), extract_dir)
        return extract_dir

    def build_index(self, match_format: str, *, force: bool = False) -> list[dict[str, Any]]:
        match_format = match_format.upper()
        if not force and match_format in self._index_cache:
            return self._index_cache[match_format]

        extract_dir = self.download_bundle(match_format, force=force)
        index: list[dict[str, Any]] = []
        for path in sorted(extract_dir.glob("*.json")):
            if path.name.startswith("README") or path.name.lower() == "all_matches.json":
                try:
                    payload = json.loads(path.read_text(encoding="utf-8"))
                except Exception:
                    continue
                if "innings" not in payload and "info" not in payload:
                    continue
            else:
                try:
                    payload = json.loads(path.read_text(encoding="utf-8"))
                except Exception as exc:  # noqa: BLE001
                    logger.warning("Could not read %s: %s", path, exc)
                    continue
            info = payload.get("info") or {}
            dates = info.get("dates") or []
            teams = info.get("teams") or []
            event = info.get("event") or {}
            index.append(
                {
                    "cricsheet_path": str(path),
                    "cricsheet_file": path.name,
                    "dates": dates,
                    "date": dates[0] if dates else None,
                    "teams": teams,
                    "teams_norm": sorted(normalize_team_name(t) for t in teams),
                    "event_name": event.get("name") if isinstance(event, dict) else None,
                    "match_type": info.get("match_type"),
                    "gender": info.get("gender"),
                    "balls_per_over": info.get("balls_per_over"),
                }
            )
        index_path = self.base_dir / f"index_{match_format.lower()}.json"
        index_path.write_text(json.dumps(index, indent=2), encoding="utf-8")
        logger.info("Cricsheet index %s entries=%s", match_format, len(index))
        self._index_cache[match_format] = index
        return index

    def find_candidates(
        self,
        *,
        match_format: str,
        match_date: str | None,
        team1: str | None,
        team2: str | None,
        match_id: str | None = None,
    ) -> list[dict[str, Any]]:
        index = self.build_index(match_format)
        wanted = {normalize_team_name(team1), normalize_team_name(team2)} - {""}

        def _identity_ok(row: dict[str, Any]) -> bool:
            if match_date and row.get("date") and row.get("date") != match_date:
                return False
            teams = set(row.get("teams_norm") or [])
            if wanted and not wanted.issubset(teams):
                return False
            return True

        # Prefer exact ESPN objectId filename when Cricsheet uses it
        if match_id:
            by_id = [row for row in index if row.get("cricsheet_file") == f"{match_id}.json"]
            if len(by_id) == 1 and _identity_ok(by_id[0]):
                return by_id
            if len(by_id) == 1 and not _identity_ok(by_id[0]):
                # Same objectId but identity mismatch — refuse rather than merge wrong match
                return []

        hits = []
        for row in index:
            if match_date and row.get("date") != match_date:
                continue
            if not _identity_ok(row):
                continue
            hits.append(row)
        return hits

    def load_deliveries_for_match(
        self,
        *,
        match_id: str,
        match_format: str,
        match_date: str | None,
        team1: str | None,
        team2: str | None,
    ) -> dict[str, Any]:
        candidates = self.find_candidates(
            match_format=match_format,
            match_date=match_date,
            team1=team1,
            team2=team2,
            match_id=match_id,
        )
        result: dict[str, Any] = {
            "match_id": match_id,
            "source_name": "Cricsheet",
            "access_status": "not_found",
            "candidates": len(candidates),
            "parse": None,
            "error": None,
            "collected_at": utc_now_iso(),
        }
        if not candidates:
            result["error"] = "No Cricsheet candidate for date/teams (or match_id file)"
            return result
        if len(candidates) > 1:
            result["access_status"] = "ambiguous"
            result["error"] = f"Multiple Cricsheet candidates ({len(candidates)}); refusing silent merge"
            result["candidate_files"] = [c["cricsheet_file"] for c in candidates]
            return result

        candidate = candidates[0]
        payload = json.loads(Path(candidate["cricsheet_path"]).read_text(encoding="utf-8"))
        parsed = parse_cricsheet_match_json(
            payload,
            match_id=match_id,
            source_url=f"cricsheet://{candidate['cricsheet_file']}",
        )
        # Persist linked deliveries
        out_dir = ensure_dir(self.project_root / "data" / "raw" / "commentary" / match_id)
        out_path = out_dir / "deliveries_cricsheet.json"
        out_path.write_text(
            json.dumps(
                {
                    "match_id": match_id,
                    "linked_cricsheet_file": candidate["cricsheet_file"],
                    "match_identity": {
                        "date": match_date,
                        "team1": team1,
                        "team2": team2,
                        "cricsheet_teams": candidate.get("teams"),
                        "cricsheet_date": candidate.get("date"),
                    },
                    "collected_at": result["collected_at"],
                    "parse": parsed,
                },
                indent=2,
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
        result["access_status"] = "ok"
        result["parse"] = {
            "parse_status": parsed.get("parse_status"),
            "ball_by_ball_status": parsed.get("ball_by_ball_status"),
            "delivery_count": len(parsed.get("deliveries") or []),
            "cricsheet_file": candidate["cricsheet_file"],
        }
        result["parsed_json_path"] = str(out_path)
        return result
