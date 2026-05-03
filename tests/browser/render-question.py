#!/usr/bin/env python3

from __future__ import annotations

import base64
import importlib.util
import json
import sys
from pathlib import Path
from unittest.mock import patch


ELEMENT_DIR = Path(__file__).resolve().parents[2]
MODULE_PATH = ELEMENT_DIR / "pl-faded-parsons.py"

if str(ELEMENT_DIR) not in sys.path:
    sys.path.insert(0, str(ELEMENT_DIR))

SPEC = importlib.util.spec_from_file_location("pl_faded_parsons", MODULE_PATH)
assert SPEC is not None
pl_faded_parsons = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(pl_faded_parsons)


def make_question_data() -> dict:
    return {
        "params": {},
        "correct_answers": {},
        "submitted_answers": {},
        "format_errors": {},
        "partial_scores": {},
        "score": 0.0,
        "feedback": {},
        "variant_seed": "seed",
        "options": {"question_path": str(ELEMENT_DIR)},
        "raw_submitted_answers": {},
        "editable": True,
        "panel": "question",
        "extensions": {},
        "num_valid_submissions": 0,
        "manual_grading": False,
        "answers_names": {},
    }


def main() -> int:
    if len(sys.argv) != 2:
        raise SystemExit("usage: render-question.py <base64-payload>")

    payload = json.loads(base64.b64decode(sys.argv[1]).decode("utf-8"))
    element_html = payload["elementHtml"]
    data = make_question_data()
    data.update(payload.get("dataOverrides", {}))
    uuid = payload.get("uuid", "uuid-123")

    with patch.object(pl_faded_parsons.pl, "get_uuid", return_value=uuid):
        rendered = pl_faded_parsons.render(element_html, data)

    sys.stdout.write(rendered)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
