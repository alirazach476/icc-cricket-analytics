"""SQLAlchemy ORM models for the CricketWorldCup Analytics warehouse.

Normalized schema with provenance columns. Players are not merged by name alone —
source identifiers are retained for identity resolution in later stages.
"""

from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    """Declarative base for all ORM models."""


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )


class ProvenanceMixin:
    source_id: Mapped[int | None] = mapped_column(
        ForeignKey("sources.source_id"), nullable=True
    )
    source_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    collected_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )


class Source(Base, TimestampMixin):
    __tablename__ = "sources"

    source_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)
    base_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    precedence: Mapped[str] = mapped_column(String(32), nullable=False, default="primary")
    attribution_required: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    collection_runs: Mapped[list[CollectionRun]] = relationship(back_populates="source")


class CollectionRun(Base, TimestampMixin):
    __tablename__ = "collection_runs"

    collection_run_id: Mapped[int] = mapped_column(
        Integer, primary_key=True, autoincrement=True
    )
    source_id: Mapped[int | None] = mapped_column(
        ForeignKey("sources.source_id"), nullable=True
    )
    pipeline_stage: Mapped[str] = mapped_column(String(64), nullable=False)
    tournament_id: Mapped[str | None] = mapped_column(
        ForeignKey("tournaments.tournament_id"), nullable=True
    )
    match_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="started")
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    finished_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    records_attempted: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    records_succeeded: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    records_failed: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    dry_run: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    source: Mapped[Source | None] = relationship(back_populates="collection_runs")


class Tournament(Base, TimestampMixin, ProvenanceMixin):
    __tablename__ = "tournaments"
    __table_args__ = (
        CheckConstraint("format IN ('ODI', 'T20')", name="ck_tournaments_format"),
        CheckConstraint("gender = 'Men'", name="ck_tournaments_gender"),
        CheckConstraint("year BETWEEN 2003 AND 2026", name="ck_tournaments_year"),
        UniqueConstraint("format", "year", "gender", name="uq_tournaments_format_year_gender"),
    )

    tournament_id: Mapped[str] = mapped_column(String(32), primary_key=True)
    tournament_name: Mapped[str] = mapped_column(String(200), nullable=False)
    year: Mapped[int] = mapped_column(Integer, nullable=False)
    format: Mapped[str] = mapped_column(String(8), nullable=False)
    gender: Mapped[str] = mapped_column(String(8), nullable=False, default="Men")
    host_country: Mapped[str | None] = mapped_column(String(200), nullable=True)
    start_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    end_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    winner: Mapped[str | None] = mapped_column(String(100), nullable=True)
    runner_up: Mapped[str | None] = mapped_column(String(100), nullable=True)
    number_of_teams: Mapped[int | None] = mapped_column(Integer, nullable=True)
    number_of_matches: Mapped[int | None] = mapped_column(Integer, nullable=True)
    collection_status: Mapped[str] = mapped_column(
        String(32), nullable=False, default="not_started"
    )
    completion_status: Mapped[str] = mapped_column(
        String(32), nullable=False, default="unknown"
    )
    metadata_notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    matches: Mapped[list[Match]] = relationship(back_populates="tournament")


class Team(Base, TimestampMixin, ProvenanceMixin):
    __tablename__ = "teams"

    team_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    team_name: Mapped[str] = mapped_column(String(120), nullable=False, unique=True)
    short_name: Mapped[str | None] = mapped_column(String(16), nullable=True)
    country_code: Mapped[str | None] = mapped_column(String(8), nullable=True)
    source_team_id: Mapped[str | None] = mapped_column(String(64), nullable=True)

    __table_args__ = (
        Index("ix_teams_source_team_id", "source_team_id"),
    )


class Player(Base, TimestampMixin, ProvenanceMixin):
    __tablename__ = "players"
    __table_args__ = (
        UniqueConstraint(
            "source_name",
            "source_player_id",
            name="uq_players_source_identity",
        ),
        Index("ix_players_full_name", "full_name"),
    )

    player_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    full_name: Mapped[str] = mapped_column(String(200), nullable=False)
    source_name: Mapped[str] = mapped_column(String(64), nullable=False, default="ESPNcricinfo")
    source_player_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    batting_style: Mapped[str | None] = mapped_column(String(64), nullable=True)
    bowling_style: Mapped[str | None] = mapped_column(String(64), nullable=True)
    date_of_birth: Mapped[date | None] = mapped_column(Date, nullable=True)
    # Do not merge players solely because names match.


class Match(Base, TimestampMixin, ProvenanceMixin):
    __tablename__ = "matches"
    __table_args__ = (
        Index("ix_matches_tournament_id", "tournament_id"),
        Index("ix_matches_match_date", "match_date"),
        UniqueConstraint("tournament_id", "source_match_id", name="uq_matches_tournament_source"),
    )

    match_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    tournament_id: Mapped[str] = mapped_column(
        ForeignKey("tournaments.tournament_id"), nullable=False
    )
    source_match_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    match_number: Mapped[int | None] = mapped_column(Integer, nullable=True)
    match_stage: Mapped[str | None] = mapped_column(String(64), nullable=True)
    match_type: Mapped[str | None] = mapped_column(String(64), nullable=True)
    match_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    start_time: Mapped[str | None] = mapped_column(String(32), nullable=True)
    venue: Mapped[str | None] = mapped_column(String(200), nullable=True)
    city: Mapped[str | None] = mapped_column(String(120), nullable=True)
    team1_id: Mapped[str | None] = mapped_column(ForeignKey("teams.team_id"), nullable=True)
    team2_id: Mapped[str | None] = mapped_column(ForeignKey("teams.team_id"), nullable=True)
    toss_winner_id: Mapped[str | None] = mapped_column(
        ForeignKey("teams.team_id"), nullable=True
    )
    toss_decision: Mapped[str | None] = mapped_column(String(32), nullable=True)
    winner_id: Mapped[str | None] = mapped_column(ForeignKey("teams.team_id"), nullable=True)
    result_type: Mapped[str | None] = mapped_column(String(64), nullable=True)
    result_margin: Mapped[str | None] = mapped_column(String(120), nullable=True)
    player_of_match_id: Mapped[str | None] = mapped_column(
        ForeignKey("players.player_id"), nullable=True
    )
    umpires: Mapped[str | None] = mapped_column(Text, nullable=True)
    match_referee: Mapped[str | None] = mapped_column(String(200), nullable=True)
    scorecard_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    commentary_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    ball_by_ball_status: Mapped[str] = mapped_column(
        String(32), nullable=False, default="not_checked"
    )
    scorecard_status: Mapped[str] = mapped_column(
        String(32), nullable=False, default="not_checked"
    )
    match_status: Mapped[str | None] = mapped_column(String(64), nullable=True)

    tournament: Mapped[Tournament] = relationship(back_populates="matches")
    innings: Mapped[list[Innings]] = relationship(back_populates="match")


class MatchTeam(Base, TimestampMixin):
    __tablename__ = "match_teams"
    __table_args__ = (
        UniqueConstraint("match_id", "team_id", name="uq_match_teams_match_team"),
    )

    match_team_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    match_id: Mapped[str] = mapped_column(ForeignKey("matches.match_id"), nullable=False)
    team_id: Mapped[str] = mapped_column(ForeignKey("teams.team_id"), nullable=False)
    is_home: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    batting_order: Mapped[int | None] = mapped_column(Integer, nullable=True)


class Innings(Base, TimestampMixin, ProvenanceMixin):
    __tablename__ = "innings"
    __table_args__ = (
        UniqueConstraint("match_id", "innings_number", name="uq_innings_match_number"),
        Index("ix_innings_match_id", "match_id"),
    )

    innings_id: Mapped[str] = mapped_column(String(80), primary_key=True)
    match_id: Mapped[str] = mapped_column(ForeignKey("matches.match_id"), nullable=False)
    innings_number: Mapped[int] = mapped_column(Integer, nullable=False)
    innings_type: Mapped[str] = mapped_column(String(32), nullable=False, default="standard")
    batting_team_id: Mapped[str | None] = mapped_column(
        ForeignKey("teams.team_id"), nullable=True
    )
    bowling_team_id: Mapped[str | None] = mapped_column(
        ForeignKey("teams.team_id"), nullable=True
    )
    total_runs: Mapped[int | None] = mapped_column(Integer, nullable=True)
    wickets: Mapped[int | None] = mapped_column(Integer, nullable=True)
    overs: Mapped[float | None] = mapped_column(Float, nullable=True)
    extras: Mapped[int | None] = mapped_column(Integer, nullable=True)
    declared: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    is_super_over: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    target: Mapped[int | None] = mapped_column(Integer, nullable=True)

    match: Mapped[Match] = relationship(back_populates="innings")
    deliveries: Mapped[list[Delivery]] = relationship(back_populates="innings")


class Delivery(Base, TimestampMixin, ProvenanceMixin):
    __tablename__ = "deliveries"
    __table_args__ = (
        UniqueConstraint(
            "match_id",
            "innings_number",
            "delivery_sequence",
            name="uq_deliveries_sequence",
        ),
        Index("ix_deliveries_match_innings", "match_id", "innings_number"),
        CheckConstraint("batter_runs >= 0", name="ck_deliveries_batter_runs"),
        CheckConstraint("extra_runs >= 0", name="ck_deliveries_extra_runs"),
        CheckConstraint("total_runs >= 0", name="ck_deliveries_total_runs"),
    )

    delivery_id: Mapped[str] = mapped_column(String(96), primary_key=True)
    match_id: Mapped[str] = mapped_column(ForeignKey("matches.match_id"), nullable=False)
    innings_id: Mapped[str] = mapped_column(ForeignKey("innings.innings_id"), nullable=False)
    innings_number: Mapped[int] = mapped_column(Integer, nullable=False)
    innings_type: Mapped[str | None] = mapped_column(String(32), nullable=True)
    over_number: Mapped[int | None] = mapped_column(Integer, nullable=True)
    ball_number: Mapped[int | None] = mapped_column(Integer, nullable=True)
    delivery_sequence: Mapped[int] = mapped_column(Integer, nullable=False)
    legal_ball_number: Mapped[int | None] = mapped_column(Integer, nullable=True)
    batter_id: Mapped[str | None] = mapped_column(
        ForeignKey("players.player_id"), nullable=True
    )
    non_striker_id: Mapped[str | None] = mapped_column(
        ForeignKey("players.player_id"), nullable=True
    )
    bowler_id: Mapped[str | None] = mapped_column(
        ForeignKey("players.player_id"), nullable=True
    )
    batter_runs: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    extra_runs: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    total_runs: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    extras_type: Mapped[str | None] = mapped_column(String(32), nullable=True)
    is_wide: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    is_no_ball: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    is_bye: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    is_leg_bye: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    is_penalty: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    is_wicket: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    dismissal_type: Mapped[str | None] = mapped_column(String(64), nullable=True)
    dismissed_player_id: Mapped[str | None] = mapped_column(
        ForeignKey("players.player_id"), nullable=True
    )
    fielder_id: Mapped[str | None] = mapped_column(
        ForeignKey("players.player_id"), nullable=True
    )
    commentary_text: Mapped[str | None] = mapped_column(Text, nullable=True)

    innings: Mapped[Innings] = relationship(back_populates="deliveries")


class BattingScorecard(Base, TimestampMixin, ProvenanceMixin):
    __tablename__ = "batting_scorecards"
    __table_args__ = (
        UniqueConstraint(
            "match_id",
            "innings_number",
            "player_id",
            name="uq_batting_scorecard_row",
        ),
    )

    batting_scorecard_id: Mapped[int] = mapped_column(
        Integer, primary_key=True, autoincrement=True
    )
    match_id: Mapped[str] = mapped_column(ForeignKey("matches.match_id"), nullable=False)
    innings_id: Mapped[str | None] = mapped_column(
        ForeignKey("innings.innings_id"), nullable=True
    )
    innings_number: Mapped[int] = mapped_column(Integer, nullable=False)
    player_id: Mapped[str] = mapped_column(ForeignKey("players.player_id"), nullable=False)
    player_name: Mapped[str | None] = mapped_column(String(200), nullable=True)
    team_id: Mapped[str | None] = mapped_column(ForeignKey("teams.team_id"), nullable=True)
    batting_position: Mapped[int | None] = mapped_column(Integer, nullable=True)
    runs: Mapped[int | None] = mapped_column(Integer, nullable=True)
    balls_faced: Mapped[int | None] = mapped_column(Integer, nullable=True)
    fours: Mapped[int | None] = mapped_column(Integer, nullable=True)
    sixes: Mapped[int | None] = mapped_column(Integer, nullable=True)
    strike_rate: Mapped[float | None] = mapped_column(Float, nullable=True)
    dismissal: Mapped[str | None] = mapped_column(Text, nullable=True)
    dismissal_type: Mapped[str | None] = mapped_column(String(64), nullable=True)
    dismissed_by: Mapped[str | None] = mapped_column(String(200), nullable=True)
    fielder: Mapped[str | None] = mapped_column(String(200), nullable=True)


class BowlingScorecard(Base, TimestampMixin, ProvenanceMixin):
    __tablename__ = "bowling_scorecards"
    __table_args__ = (
        UniqueConstraint(
            "match_id",
            "innings_number",
            "player_id",
            name="uq_bowling_scorecard_row",
        ),
    )

    bowling_scorecard_id: Mapped[int] = mapped_column(
        Integer, primary_key=True, autoincrement=True
    )
    match_id: Mapped[str] = mapped_column(ForeignKey("matches.match_id"), nullable=False)
    innings_id: Mapped[str | None] = mapped_column(
        ForeignKey("innings.innings_id"), nullable=True
    )
    innings_number: Mapped[int] = mapped_column(Integer, nullable=False)
    player_id: Mapped[str] = mapped_column(ForeignKey("players.player_id"), nullable=False)
    player_name: Mapped[str | None] = mapped_column(String(200), nullable=True)
    team_id: Mapped[str | None] = mapped_column(ForeignKey("teams.team_id"), nullable=True)
    overs: Mapped[float | None] = mapped_column(Float, nullable=True)
    maidens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    runs_conceded: Mapped[int | None] = mapped_column(Integer, nullable=True)
    wickets: Mapped[int | None] = mapped_column(Integer, nullable=True)
    economy: Mapped[float | None] = mapped_column(Float, nullable=True)
    dots: Mapped[int | None] = mapped_column(Integer, nullable=True)
    wides: Mapped[int | None] = mapped_column(Integer, nullable=True)
    no_balls: Mapped[int | None] = mapped_column(Integer, nullable=True)


class FieldingScorecard(Base, TimestampMixin, ProvenanceMixin):
    __tablename__ = "fielding_scorecards"
    __table_args__ = (
        UniqueConstraint(
            "match_id",
            "player_id",
            name="uq_fielding_scorecard_row",
        ),
    )

    fielding_scorecard_id: Mapped[int] = mapped_column(
        Integer, primary_key=True, autoincrement=True
    )
    match_id: Mapped[str] = mapped_column(ForeignKey("matches.match_id"), nullable=False)
    player_id: Mapped[str] = mapped_column(ForeignKey("players.player_id"), nullable=False)
    player_name: Mapped[str | None] = mapped_column(String(200), nullable=True)
    team_id: Mapped[str | None] = mapped_column(ForeignKey("teams.team_id"), nullable=True)
    catches: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    run_outs: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    stumpings: Mapped[int] = mapped_column(Integer, nullable=False, default=0)


class Standing(Base, TimestampMixin, ProvenanceMixin):
    __tablename__ = "standings"
    __table_args__ = (
        UniqueConstraint(
            "tournament_id",
            "group_name",
            "team_id",
            name="uq_standings_group_team",
        ),
    )

    standing_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    tournament_id: Mapped[str] = mapped_column(
        ForeignKey("tournaments.tournament_id"), nullable=False
    )
    group_name: Mapped[str] = mapped_column(String(64), nullable=False, default="Overall")
    team_id: Mapped[str] = mapped_column(ForeignKey("teams.team_id"), nullable=False)
    matches_played: Mapped[int | None] = mapped_column(Integer, nullable=True)
    wins: Mapped[int | None] = mapped_column(Integer, nullable=True)
    losses: Mapped[int | None] = mapped_column(Integer, nullable=True)
    ties: Mapped[int | None] = mapped_column(Integer, nullable=True)
    no_results: Mapped[int | None] = mapped_column(Integer, nullable=True)
    points: Mapped[float | None] = mapped_column(Float, nullable=True)
    net_run_rate: Mapped[float | None] = mapped_column(Float, nullable=True)
    position: Mapped[int | None] = mapped_column(Integer, nullable=True)
    qualified: Mapped[bool | None] = mapped_column(Boolean, nullable=True)


class Squad(Base, TimestampMixin, ProvenanceMixin):
    """A player's membership of a team's squad for one tournament edition."""

    __tablename__ = "squads"
    __table_args__ = (
        UniqueConstraint(
            "tournament_id",
            "team_id",
            "player_id",
            name="uq_squads_tournament_team_player",
        ),
        Index("ix_squads_tournament_team", "tournament_id", "team_id"),
    )

    squad_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    tournament_id: Mapped[str] = mapped_column(
        ForeignKey("tournaments.tournament_id"), nullable=False
    )
    team_id: Mapped[str] = mapped_column(ForeignKey("teams.team_id"), nullable=False)
    player_id: Mapped[str] = mapped_column(ForeignKey("players.player_id"), nullable=False)
    role_code: Mapped[str | None] = mapped_column(String(8), nullable=True)
    is_captain: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    is_wicketkeeper: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    playing_roles: Mapped[str | None] = mapped_column(String(120), nullable=True)
    announced_at: Mapped[date | None] = mapped_column(Date, nullable=True)
    is_withdrawn: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)


class TournamentAward(Base, TimestampMixin, ProvenanceMixin):
    __tablename__ = "tournament_awards"
    __table_args__ = (
        UniqueConstraint(
            "tournament_id",
            "award_type",
            "player_id",
            name="uq_tournament_award",
        ),
    )

    award_id: Mapped[str] = mapped_column(String(80), primary_key=True)
    tournament_id: Mapped[str] = mapped_column(
        ForeignKey("tournaments.tournament_id"), nullable=False
    )
    award_type: Mapped[str] = mapped_column(String(64), nullable=False)
    player_id: Mapped[str | None] = mapped_column(
        ForeignKey("players.player_id"), nullable=True
    )
    team_id: Mapped[str | None] = mapped_column(ForeignKey("teams.team_id"), nullable=True)
    award_name: Mapped[str] = mapped_column(String(200), nullable=False)


class MatchEvent(Base, TimestampMixin, ProvenanceMixin):
    __tablename__ = "match_events"
    __table_args__ = (
        Index("ix_match_events_match_id", "match_id"),
        Index("ix_match_events_tournament_id", "tournament_id"),
    )

    event_id: Mapped[str] = mapped_column(String(80), primary_key=True)
    tournament_id: Mapped[str] = mapped_column(
        ForeignKey("tournaments.tournament_id"), nullable=False
    )
    match_id: Mapped[str | None] = mapped_column(
        ForeignKey("matches.match_id"), nullable=True
    )
    event_type: Mapped[str] = mapped_column(String(64), nullable=False)
    event_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    team_id: Mapped[str | None] = mapped_column(ForeignKey("teams.team_id"), nullable=True)
    player_id: Mapped[str | None] = mapped_column(
        ForeignKey("players.player_id"), nullable=True
    )
    description: Mapped[str | None] = mapped_column(Text, nullable=True)


class DataQualityResult(Base, TimestampMixin):
    __tablename__ = "data_quality_results"
    __table_args__ = (
        Index("ix_dqr_entity", "entity_type", "entity_id"),
        Index("ix_dqr_severity", "severity"),
    )

    result_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    collection_run_id: Mapped[int | None] = mapped_column(
        ForeignKey("collection_runs.collection_run_id"), nullable=True
    )
    entity_type: Mapped[str] = mapped_column(String(64), nullable=False)
    entity_id: Mapped[str | None] = mapped_column(String(96), nullable=True)
    tournament_id: Mapped[str | None] = mapped_column(
        ForeignKey("tournaments.tournament_id"), nullable=True
    )
    check_name: Mapped[str] = mapped_column(String(120), nullable=False)
    severity: Mapped[str] = mapped_column(String(16), nullable=False)  # error|warning|info
    status: Mapped[str] = mapped_column(String(16), nullable=False)  # pass|fail|skip
    message: Mapped[str | None] = mapped_column(Text, nullable=True)
    details_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Never auto-discard questionable records; preserve raw + log issues.
