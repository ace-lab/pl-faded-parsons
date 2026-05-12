from __future__ import annotations

import sys
from pathlib import Path


TEST_DIR = Path(__file__).resolve().parent
ELEMENT_DIR = TEST_DIR.parents[1]
FPPGEN_DIR = ELEMENT_DIR / "fppgen"

for candidate in (str(ELEMENT_DIR), str(FPPGEN_DIR)):
    if candidate not in sys.path:
        sys.path.insert(0, candidate)
