import importlib.util
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


ELEMENT_DIR = Path(__file__).resolve().parents[1]
MODULE_PATH = ELEMENT_DIR / "pl-faded-parsons.py"

if str(ELEMENT_DIR) not in sys.path:
    sys.path.insert(0, str(ELEMENT_DIR))

SPEC = importlib.util.spec_from_file_location("pl_faded_parsons", MODULE_PATH)
assert SPEC is not None
pl_faded_parsons = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(pl_faded_parsons)


def make_question_data(tmp_path: Path) -> dict:
    return {
        "params": {},
        "correct_answers": {},
        "submitted_answers": {},
        "format_errors": {},
        "partial_scores": {},
        "score": 0.0,
        "feedback": {},
        "variant_seed": "seed",
        "options": {"question_path": str(tmp_path)},
        "raw_submitted_answers": {},
        "editable": True,
        "panel": "question",
        "extensions": {},
        "num_valid_submissions": 1,
        "manual_grading": False,
        "answers_names": {},
    }


class TestReloadIndentRegression(unittest.TestCase):
    def test_saved_indent_level_rerenders_as_logical_indent_property(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            tmp_path = Path(temp_dir)
            data = make_question_data(tmp_path)
            data["raw_submitted_answers"] = {
                "demo.main": json.dumps(
                    {
                        "solution": [
                            {
                                "indent": 1,
                                "codeSnippets": ["return x"],
                                "blankValues": [],
                            }
                        ],
                        "starter": [],
                    }
                ),
                "demo.log": "[]",
            }

            element_html = (
                '<pl-faded-parsons answers-name="demo" language="python">'
                "</pl-faded-parsons>"
            )

            with patch.object(pl_faded_parsons.pl, "get_uuid", return_value="uuid-123"):
                prev_cwd = os.getcwd()
                try:
                    os.chdir(ELEMENT_DIR)
                    rendered = pl_faded_parsons.render(element_html, data)
                finally:
                    os.chdir(prev_cwd)

        self.assertIn('style="--pl-faded-parsons-indent: 1;"', rendered)


if __name__ == "__main__":
    unittest.main()
