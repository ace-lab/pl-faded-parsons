#!/usr/bin/env python3

from __future__ import annotations

import base64
import importlib.util
import json
import sys
import traceback
from pathlib import Path
from unittest.mock import patch

import lxml.html as xml


ELEMENT_DIR = Path(__file__).resolve().parents[2]
MODULE_PATH = ELEMENT_DIR / "pl-faded-parsons.py"

if str(ELEMENT_DIR) not in sys.path:
    sys.path.insert(0, str(ELEMENT_DIR))

SPEC = importlib.util.spec_from_file_location("pl_faded_parsons", MODULE_PATH)
assert SPEC is not None
pl_faded_parsons = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(pl_faded_parsons)


def _extract_raw_submitted_answers(element_html: str) -> dict[str, str]:
    root = xml.fragment_fromstring(element_html)
    raw_answers: dict[str, str] = {}

    for input_element in root.xpath(".//input[@name]"):
        name = input_element.get("name")
        if name:
            raw_answers[name] = input_element.get("value", "")

    return raw_answers


def main() -> int:
    if len(sys.argv) != 2:
        raise SystemExit("usage: parse-question.py <base64-payload>")

    try:
        payload = json.loads(base64.b64decode(sys.argv[1]).decode("utf-8"))
        element_html = payload["elementHtml"]
        data = pl_faded_parsons.pl._make_question_data(str(ELEMENT_DIR))
        data_overrides = dict(payload.get("dataOverrides", {}))
        raw_submitted_answers = data_overrides.pop("rawSubmittedAnswers", None)
        data.update(data_overrides)
        data["panel"] = "parse"
        data["raw_submitted_answers"] = (
            raw_submitted_answers
            if raw_submitted_answers is not None
            else _extract_raw_submitted_answers(element_html)
        )
        uuid = payload.get("uuid", "uuid-123")
        lifecycle_data = pl_faded_parsons.pl._LifecycleData(data)

        with patch.object(pl_faded_parsons.pl, "get_uuid", return_value=uuid):
            lifecycle_data.set_phase("prepare")
            pl_faded_parsons.prepare(element_html, lifecycle_data)
            lifecycle_data.set_phase("parse")
            pl_faded_parsons.parse(element_html, lifecycle_data)

        sys.stdout.write(json.dumps(data))
        return 0
    except Exception:
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
