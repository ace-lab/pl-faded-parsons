from __future__ import annotations

import os
import random
import sys
from types import ModuleType
from pathlib import Path
from unittest.mock import patch


BROWSER_DIR = Path(__file__).resolve().parent
ELEMENT_DIR = BROWSER_DIR.parent.parent
MODULE_PATH = ELEMENT_DIR / "pl-faded-parsons.py"
BANNED_IMPORT_GLOBALS = {"__file__", "__spec__", "__loader__", "__package__", "__cached__"}

if str(ELEMENT_DIR) not in sys.path:
    sys.path.insert(0, str(ELEMENT_DIR))


def load_controller_module() -> ModuleType:
    """Execute the controller without PrairieLearn import metadata globals."""

    module = ModuleType("pl_faded_parsons")
    for key in BANNED_IMPORT_GLOBALS:
        module.__dict__.pop(key, None)
    sys.modules[module.__name__] = module
    source = MODULE_PATH.read_text(encoding="utf-8")
    try:
        exec(compile(source, str(MODULE_PATH), "exec"), module.__dict__)
    except Exception:
        sys.modules.pop(module.__name__, None)
        raise
    return module


pl_faded_parsons = load_controller_module()


def render_question_html(
    element_html: str,
    *,
    data_overrides: dict[str, object] | None = None,
    uuid: str = "uuid-123",
    question_dir: Path | None = None,
    panel: str = "question",
) -> str:
    """Render a pl-faded-parsons element using the current Python controller."""

    data = pl_faded_parsons.pl._make_question_data(
        str(question_dir or ELEMENT_DIR)
    )
    data.update(data_overrides or {})
    data["panel"] = panel
    random.seed(data["variant_seed"])
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
