"""The selected competition must be per request: concurrent requests must never read each other's database."""

from __future__ import annotations

import sys
import threading
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.utils import database  # noqa: E402


def test_competition_is_isolated_between_threads() -> None:
    expected = {"ct": 112, "wtc": 245, "wc": 719}
    errors: list[str] = []
    barrier = threading.Barrier(3)

    def worker(code: str) -> None:
        database.set_competition(code)
        barrier.wait()
        for _ in range(40):
            n = int(database.run("select count(*) n from gold.fact_matches").iloc[0, 0])
            if n != expected[code] or database.competition() != code:
                errors.append(f"{code}: saw {n} matches, competition {database.competition()}")
                return

    threads = [threading.Thread(target=worker, args=(c,)) for c in expected]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert not errors, errors


def test_setting_a_competition_in_a_thread_does_not_change_the_caller() -> None:
    database.set_competition("wc")

    def other() -> None:
        database.set_competition("wtc")

    t = threading.Thread(target=other)
    t.start()
    t.join()
    assert database.competition() == "wc"
