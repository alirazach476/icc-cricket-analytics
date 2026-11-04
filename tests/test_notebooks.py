"""Stage 9: the committed EDA notebooks are executed, error-free and contain charts and findings."""

from __future__ import annotations

from pathlib import Path

import nbformat
import pytest

NB_DIR = Path(__file__).resolve().parents[1] / "notebooks"
NOTEBOOKS = sorted(NB_DIR.glob("0*.ipynb"))

pytestmark = pytest.mark.skipif(len(NOTEBOOKS) < 3, reason="notebooks not built")


@pytest.mark.parametrize("path", NOTEBOOKS, ids=lambda p: p.stem)
def test_notebook_executed_without_errors(path: Path) -> None:
    nb = nbformat.read(path, 4)
    code = [c for c in nb.cells if c.cell_type == "code"]
    assert code and all(c.execution_count for c in code), "not fully executed"
    errors = [o for c in code for o in c.outputs if o.output_type == "error"]
    assert not errors, errors[:1]
    figures = sum("image/png" in o.get("data", {}) for c in code for o in c.outputs)
    assert figures >= 3, f"only {figures} figures"


def test_findings_are_computed_not_typed() -> None:
    text = "".join(
        o.get("text", "")
        for p in NOTEBOOKS
        for c in nbformat.read(p, 4).cells
        if c.cell_type == "code"
        for o in c.outputs
    )
    assert text.count("FINDING") >= 8
