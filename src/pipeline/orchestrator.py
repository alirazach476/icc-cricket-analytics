"""Stage 10 incremental pipeline: normalize → validate → load (optional collect)."""

from __future__ import annotations

import json
from collections.abc import Callable
from typing import Any

from src.utils.config import get_project_root
from src.utils.helpers import ensure_dir, utc_now_iso
from src.utils.logger import get_logger

logger = get_logger(__name__)

STAGE_ORDER = (
    "collect_scorecards",
    "collect_commentary",
    "normalize",
    "validate",
    "load",
    "warehouse",
    "dbt",
)


def run_pipeline(
    *,
    tournament_id: str | None = None,
    match_ids: list[str] | None = None,
    limit: int | None = None,
    stages: list[str] | None = None,
    dry_run: bool = False,
    force: bool = False,
    source: str = "cricsheet",
    skip_collect: bool = True,
) -> dict[str, Any]:
    """Run selected pipeline stages in order.

    By default collection stages are skipped (data assumed already collected)
    unless ``skip_collect=False``.
    """
    selected = list(stages or ["normalize", "validate", "load", "warehouse"])
    if skip_collect:
        selected = [s for s in selected if s not in {"collect_scorecards", "collect_commentary"}]

    unknown = [s for s in selected if s not in STAGE_ORDER]
    if unknown:
        raise ValueError(f"Unknown pipeline stages: {unknown}")

    started = utc_now_iso()
    stage_reports: dict[str, Any] = {}

    for stage in STAGE_ORDER:
        if stage not in selected:
            continue
        logger.info("Pipeline stage starting: %s", stage)
        if dry_run and stage == "load":
            from src.database.load_processed import load_processed

            stage_reports[stage] = load_processed(
                tournament_id=tournament_id,
                match_ids=match_ids,
                limit=limit,
                dry_run=True,
            )
            continue
        if dry_run and stage in {"warehouse", "dbt"}:
            stage_reports[stage] = {"dry_run": True, "skipped": True}
            continue
        if dry_run and stage in {"collect_scorecards", "collect_commentary"}:
            stage_reports[stage] = {"dry_run": True, "skipped_network": True}
            continue

        handler = _STAGE_HANDLERS[stage]
        stage_reports[stage] = handler(
            tournament_id=tournament_id,
            match_ids=match_ids,
            limit=limit,
            force=force,
            source=source,
            dry_run=dry_run,
        )
        logger.info("Pipeline stage finished: %s", stage)

    report = {
        "started_at": started,
        "finished_at": utc_now_iso(),
        "tournament_id": tournament_id,
        "stages": selected,
        "dry_run": dry_run,
        "stage_reports": stage_reports,
    }
    root = get_project_root()
    path = ensure_dir(root / "data" / "processed" / "validation") / (
        f"pipeline_report_{tournament_id or 'all'}.json"
    )
    path.write_text(json.dumps(report, indent=2, ensure_ascii=False, default=str), encoding="utf-8")
    report["report_path"] = str(path)
    return report


def _run_collect_scorecards(**kwargs: Any) -> dict[str, Any]:
    from src.collectors.scorecard_collector import collect_scorecards

    return collect_scorecards(
        tournament_id=kwargs.get("tournament_id"),
        match_ids=kwargs.get("match_ids"),
        limit=kwargs.get("limit"),
        force=bool(kwargs.get("force")),
        live=not bool(kwargs.get("dry_run")),
    )


def _run_collect_commentary(**kwargs: Any) -> dict[str, Any]:
    from src.collectors.commentary_collector import collect_commentary

    return collect_commentary(
        tournament_id=kwargs.get("tournament_id"),
        match_ids=kwargs.get("match_ids"),
        limit=kwargs.get("limit"),
        source=kwargs.get("source") or "cricsheet",
        force=bool(kwargs.get("force")),
        live=not bool(kwargs.get("dry_run")),
    )


def _run_normalize(**kwargs: Any) -> dict[str, Any]:
    from src.transformations.normalize_collected import normalize_collected

    return normalize_collected(
        tournament_id=kwargs.get("tournament_id"),
        match_ids=kwargs.get("match_ids"),
        limit=kwargs.get("limit"),
        force=bool(kwargs.get("force")),
    )


def _run_validate(**kwargs: Any) -> dict[str, Any]:
    from src.validation.validate_dataset import validate_dataset

    return validate_dataset(
        tournament_id=kwargs.get("tournament_id"),
        match_ids=kwargs.get("match_ids"),
        limit=kwargs.get("limit"),
        include_coverage=True,
    )


def _run_load(**kwargs: Any) -> dict[str, Any]:
    from src.database.load_processed import load_processed

    return load_processed(
        tournament_id=kwargs.get("tournament_id"),
        match_ids=kwargs.get("match_ids"),
        limit=kwargs.get("limit"),
        dry_run=bool(kwargs.get("dry_run")),
    )


def _run_warehouse(**kwargs: Any) -> dict[str, Any]:
    from src.warehouse.duckdb_warehouse import sync_warehouse

    return sync_warehouse(
        tournament_id=kwargs.get("tournament_id"),
        write_parquet=True,
        replace_duckdb=bool(kwargs.get("force")),
    )


def _run_dbt(**kwargs: Any) -> dict[str, Any]:
    import subprocess

    root = get_project_root()
    dbt_dir = root / "dbt"
    dbt_exe = root / ".venv" / "Scripts" / "dbt.exe"
    if not dbt_exe.exists():
        dbt_exe = root / ".venv" / "bin" / "dbt"
    target = "odi_2023" if kwargs.get("tournament_id") == "ODI_M_2023" else "dev"
    cmd = [
        str(dbt_exe) if dbt_exe.exists() else "dbt",
        "build",
        "--project-dir",
        str(dbt_dir),
        "--profiles-dir",
        str(dbt_dir),
        "--target",
        target,
    ]
    if kwargs.get("tournament_id"):
        cmd.extend(["--vars", f'{{"tournament_id": "{kwargs["tournament_id"]}"}}'])
    completed = subprocess.run(cmd, cwd=str(root), capture_output=True, text=True)
    return {
        "returncode": completed.returncode,
        "target": target,
        "stdout_tail": (completed.stdout or "")[-2000:],
        "stderr_tail": (completed.stderr or "")[-1000:],
        "ok": completed.returncode == 0,
    }


_STAGE_HANDLERS: dict[str, Callable[..., dict[str, Any]]] = {
    "collect_scorecards": _run_collect_scorecards,
    "collect_commentary": _run_collect_commentary,
    "normalize": _run_normalize,
    "validate": _run_validate,
    "load": _run_load,
    "warehouse": _run_warehouse,
    "dbt": _run_dbt,
}
