#!/usr/bin/env python3

from __future__ import annotations

import base64
import json
import sys
import traceback
from pathlib import Path

from render_core import render_question_html


ELEMENT_DIR = Path(__file__).resolve().parents[2]


def main() -> int:
    if len(sys.argv) != 2:
        raise SystemExit("usage: render-question.py <base64-payload>")

    try:
        payload = json.loads(base64.b64decode(sys.argv[1]).decode("utf-8"))
        rendered = render_question_html(
            payload["elementHtml"],
            data_overrides=payload.get("dataOverrides", {}),
            uuid=payload.get("uuid", "uuid-123"),
            question_dir=ELEMENT_DIR,
        )
        sys.stdout.write(rendered)
        return 0
    except Exception:
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
