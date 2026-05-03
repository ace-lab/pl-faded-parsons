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


def main() -> int:
    if len(sys.argv) != 2:
        raise SystemExit("usage: render-question.py <base64-payload>")

    try:
        payload = json.loads(base64.b64decode(sys.argv[1]).decode("utf-8"))
        element_html = payload["elementHtml"]
        data = pl_faded_parsons.pl._make_question_data(str(ELEMENT_DIR))
        data.update(payload.get("dataOverrides", {}))
        uuid = payload.get("uuid", "uuid-123")
        lifecycle_data = pl_faded_parsons.pl._LifecycleData(data)

        with patch.object(pl_faded_parsons.pl, "get_uuid", return_value=uuid):
            # PrairieLearn runs prepare() before render(); the docs for element
            # functions specify that prepare() validates and prepares initial data
            # after generate(), then render() consumes that prepared state.
            lifecycle_data.set_phase("prepare")
            pl_faded_parsons.prepare(element_html, lifecycle_data)
            lifecycle_data.set_phase("render")
            rendered = pl_faded_parsons.render(element_html, lifecycle_data)

        sys.stdout.write(rendered)
        return 0
    except Exception:
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
