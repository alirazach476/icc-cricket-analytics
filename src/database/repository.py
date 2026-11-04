"""Repository helpers with transactional upserts."""

from __future__ import annotations

from collections.abc import Iterable
from datetime import UTC, date, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from src.database.models import (
    BattingScorecard,
    BowlingScorecard,
    CollectionRun,
    DataQualityResult,
    Delivery,
    FieldingScorecard,
    Innings,
    Match,
    MatchTeam,
    Player,
    Source,
    Team,
    Tournament,
)
from src.utils.logger import get_logger

logger = get_logger(__name__)


def upsert_source(session: Session, *, name: str, **fields: Any) -> Source:
    """Insert or update a named data source."""
    stmt = insert(Source).values(name=name, **fields)
    update_cols = {key: stmt.excluded[key] for key in fields}
    stmt = stmt.on_conflict_do_update(index_elements=[Source.name], set_=update_cols)
    session.execute(stmt)
    session.flush()
    source = session.scalar(select(Source).where(Source.name == name))
    assert source is not None
    return source


def upsert_tournament(session: Session, payload: dict[str, Any]) -> None:
    """Upsert a tournament row by primary key."""
    stmt = insert(Tournament).values(**payload)
    update_cols = {key: stmt.excluded[key] for key in payload if key != "tournament_id"}
    stmt = stmt.on_conflict_do_update(
        index_elements=[Tournament.tournament_id],
        set_=update_cols,
    )
    session.execute(stmt)


def upsert_tournaments(session: Session, rows: Iterable[dict[str, Any]]) -> int:
    count = 0
    for row in rows:
        upsert_tournament(session, row)
        count += 1
    logger.info("Upserted %s tournament rows", count)
    return count


def get_tournament(session: Session, tournament_id: str) -> Tournament | None:
    return session.get(Tournament, tournament_id)


def list_tournaments(session: Session) -> list[Tournament]:
    return list(session.scalars(select(Tournament).order_by(Tournament.year, Tournament.format)))


def parse_optional_date(value: str | date | None) -> date | None:
    if value is None or value == "":
        return None
    if isinstance(value, date) and not isinstance(value, datetime):
        return value
    if isinstance(value, datetime):
        return value.date()
    text = str(value).strip()
    if not text:
        return None
    return date.fromisoformat(text[:10])


def parse_optional_datetime(value: str | datetime | None) -> datetime | None:
    if value is None or value == "":
        return None
    if isinstance(value, datetime):
        return value
    text = str(value).strip().replace("Z", "+00:00")
    try:
        return datetime.fromisoformat(text)
    except ValueError:
        return None


def tournament_payload_from_registry(record: Any, source_id: int | None = None) -> dict[str, Any]:
    """Map a TournamentRecord / dict into a DB payload."""
    if hasattr(record, "model_dump"):
        data = record.model_dump(mode="json")
    else:
        data = dict(record)

    return {
        "tournament_id": data["tournament_id"],
        "tournament_name": data["tournament_name"],
        "year": int(data["year"]),
        "format": data["format"] if isinstance(data["format"], str) else data["format"].value,
        "gender": data.get("gender", "Men"),
        "host_country": data.get("host_country"),
        "start_date": parse_optional_date(data.get("start_date")),
        "end_date": parse_optional_date(data.get("end_date")),
        "winner": data.get("winner"),
        "runner_up": data.get("runner_up"),
        "number_of_teams": data.get("number_of_teams"),
        "number_of_matches": data.get("number_of_matches"),
        "collection_status": data.get("collection_status") or "not_started",
        "completion_status": data.get("completion_status") or "unknown",
        "metadata_notes": data.get("metadata_notes") or data.get("notes"),
        "source_id": source_id,
        "source_url": str(data["source_url"]) if data.get("source_url") else None,
        "collected_at": datetime.now(UTC),
    }


def _upsert_by_pk(session: Session, model: type, payload: dict[str, Any], pk: str) -> None:
    stmt = insert(model).values(**payload)
    update_cols = {key: stmt.excluded[key] for key in payload if key != pk}
    if update_cols:
        stmt = stmt.on_conflict_do_update(index_elements=[pk], set_=update_cols)
    else:
        stmt = stmt.on_conflict_do_nothing(index_elements=[pk])
    session.execute(stmt)


def upsert_team(session: Session, payload: dict[str, Any]) -> None:
    _upsert_by_pk(session, Team, payload, "team_id")


def upsert_player(session: Session, payload: dict[str, Any]) -> None:
    _upsert_by_pk(session, Player, payload, "player_id")


def upsert_match(session: Session, payload: dict[str, Any]) -> None:
    _upsert_by_pk(session, Match, payload, "match_id")


def upsert_innings(session: Session, payload: dict[str, Any]) -> None:
    _upsert_by_pk(session, Innings, payload, "innings_id")


def upsert_delivery(session: Session, payload: dict[str, Any]) -> None:
    _upsert_by_pk(session, Delivery, payload, "delivery_id")


def upsert_match_team(session: Session, payload: dict[str, Any]) -> None:
    stmt = insert(MatchTeam).values(**payload)
    stmt = stmt.on_conflict_do_update(
        constraint="uq_match_teams_match_team",
        set_={
            "is_home": stmt.excluded.is_home,
            "batting_order": stmt.excluded.batting_order,
        },
    )
    session.execute(stmt)


def upsert_batting_scorecard(session: Session, payload: dict[str, Any]) -> None:
    stmt = insert(BattingScorecard).values(**payload)
    update_cols = {
        key: stmt.excluded[key]
        for key in payload
        if key not in {"batting_scorecard_id", "match_id", "innings_number", "player_id"}
    }
    stmt = stmt.on_conflict_do_update(constraint="uq_batting_scorecard_row", set_=update_cols)
    session.execute(stmt)


def upsert_bowling_scorecard(session: Session, payload: dict[str, Any]) -> None:
    stmt = insert(BowlingScorecard).values(**payload)
    update_cols = {
        key: stmt.excluded[key]
        for key in payload
        if key not in {"bowling_scorecard_id", "match_id", "innings_number", "player_id"}
    }
    stmt = stmt.on_conflict_do_update(constraint="uq_bowling_scorecard_row", set_=update_cols)
    session.execute(stmt)


def upsert_fielding_scorecard(session: Session, payload: dict[str, Any]) -> None:
    stmt = insert(FieldingScorecard).values(**payload)
    update_cols = {
        key: stmt.excluded[key]
        for key in payload
        if key not in {"fielding_scorecard_id", "match_id", "player_id"}
    }
    stmt = stmt.on_conflict_do_update(constraint="uq_fielding_scorecard_row", set_=update_cols)
    session.execute(stmt)


def start_collection_run(
    session: Session,
    *,
    pipeline_stage: str,
    tournament_id: str | None = None,
    match_id: str | None = None,
    source_id: int | None = None,
    dry_run: bool = False,
) -> CollectionRun:
    run = CollectionRun(
        pipeline_stage=pipeline_stage,
        tournament_id=tournament_id,
        match_id=match_id,
        source_id=source_id,
        status="started",
        dry_run=dry_run,
        started_at=datetime.now(UTC),
    )
    session.add(run)
    session.flush()
    return run


def finish_collection_run(
    session: Session,
    run: CollectionRun,
    *,
    status: str,
    attempted: int = 0,
    succeeded: int = 0,
    failed: int = 0,
    error_message: str | None = None,
) -> None:
    run.status = status
    run.records_attempted = attempted
    run.records_succeeded = succeeded
    run.records_failed = failed
    run.error_message = error_message
    run.finished_at = datetime.now(UTC)
    session.flush()


def insert_data_quality_results(
    session: Session,
    issues: list[dict[str, Any]],
    *,
    collection_run_id: int | None = None,
    tournament_id: str | None = None,
) -> int:
    count = 0
    for row in issues:
        session.add(
            DataQualityResult(
                collection_run_id=collection_run_id,
                entity_type=row.get("entity_type") or "unknown",
                entity_id=row.get("entity_id") or row.get("match_id"),
                tournament_id=tournament_id,
                check_name=row.get("code") or "unknown",
                severity=row.get("severity") or "error",
                status="fail",
                message=row.get("message"),
                details_json=str(row.get("details") or {}),
            )
        )
        count += 1
    session.flush()
    return count
