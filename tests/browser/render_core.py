from __future__ import annotations

import os
import importlib.util
import sys
from pathlib import Path
from unittest.mock import patch


BROWSER_DIR = Path(__file__).resolve().parent
ELEMENT_DIR = BROWSER_DIR.parent.parent
MODULE_PATH = ELEMENT_DIR / "pl-faded-parsons.py"

if str(ELEMENT_DIR) not in sys.path:
    sys.path.insert(0, str(ELEMENT_DIR))

SPEC = importlib.util.spec_from_file_location("pl_faded_parsons", MODULE_PATH)
assert SPEC is not None
pl_faded_parsons = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(pl_faded_parsons)


def render_question_html(
    element_html: str,
    *,
    data_overrides: dict[str, object] | None = None,
    uuid: str = "uuid-123",
    question_dir: Path | None = None,
) -> str:
    """Render a pl-faded-parsons element using the current Python controller."""

    data = pl_faded_parsons.pl._make_question_data(
        str(question_dir or ELEMENT_DIR)
    )
    data.update(data_overrides or {})
    lifecycle_data = pl_faded_parsons.pl._LifecycleData(data)

    old_cwd = Path.cwd()
    try:
        os.chdir(ELEMENT_DIR)
        with patch.object(pl_faded_parsons.pl, "get_uuid", return_value=uuid):
            lifecycle_data.set_phase("prepare")
            pl_faded_parsons.prepare(element_html, lifecycle_data)
            lifecycle_data.set_phase("render")
            return pl_faded_parsons.render(element_html, lifecycle_data)
    finally:
        os.chdir(old_cwd)
