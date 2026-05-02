import importlib.util
import base64
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


ELEMENT_DIR = Path.cwd()
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
    def test_render_disables_logging_by_default(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            tmp_path = Path(temp_dir)
            data = make_question_data(tmp_path)
            element_html = '<pl-faded-parsons answers-name="demo"></pl-faded-parsons>'

            with patch.object(pl_faded_parsons.pl, "get_uuid", return_value="uuid-123"):
                rendered = pl_faded_parsons.render(element_html, data)

        self.assertNotIn("loggingEnabled: true", rendered)
        self.assertIn('name="demo.log" type="hidden" value="[]"', rendered)

    def test_render_preserves_log_when_logging_enabled(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            tmp_path = Path(temp_dir)
            data = make_question_data(tmp_path)
            data["raw_submitted_answers"] = {
                "demo.main": json.dumps({"solution": [], "starter": []}),
                "demo.log": json.dumps(
                    [
                        {
                            "timestamp": "2024-01-01T00:00:00Z",
                            "tag": "problemOpened",
                            "data": {},
                        }
                    ]
                ),
            }
            element_html = '<pl-faded-parsons answers-name="demo" log="true"></pl-faded-parsons>'

            with patch.object(pl_faded_parsons.pl, "get_uuid", return_value="uuid-123"):
                rendered = pl_faded_parsons.render(element_html, data)

        self.assertIn("loggingEnabled: true", rendered)
        self.assertIn("problemOpened", rendered)

    def test_render_question_does_not_register_global_widget(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            tmp_path = Path(temp_dir)
            data = make_question_data(tmp_path)
            element_html = '<pl-faded-parsons answers-name="demo"></pl-faded-parsons>'

            with patch.object(pl_faded_parsons.pl, "get_uuid", return_value="uuid-123"):
                rendered = pl_faded_parsons.render(element_html, data)

        self.assertIn("new ParsonsWidget(", rendered)
        self.assertNotIn("ParsonsGlobal.widgets.push", rendered)

    def test_render_keeps_empty_starter_tray_visible_after_submission(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            tmp_path = Path(temp_dir)
            data = make_question_data(tmp_path)
            data["raw_submitted_answers"] = {
                "demo.main": json.dumps(
                    {
                        "solution": [
                            {
                                "indent": 0,
                                "codeSnippets": ["answer()"],
                                "blankValues": [],
                            }
                        ],
                        "starter": [],
                    }
                ),
                "demo.log": "[]",
            }
            element_html = '<pl-faded-parsons answers-name="demo"></pl-faded-parsons>'

            with patch.object(pl_faded_parsons.pl, "get_uuid", return_value="uuid-123"):
                rendered = pl_faded_parsons.render(element_html, data)

        self.assertIn('id="starter-code-uuid-123"', rendered)
        self.assertIn('id="ol-starter-code-uuid-123"', rendered)

    def test_render_hides_empty_starter_tray_in_no_code_format(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            tmp_path = Path(temp_dir)
            data = make_question_data(tmp_path)
            data["raw_submitted_answers"] = {
                "demo.main": json.dumps(
                    {
                        "solution": [
                            {
                                "indent": 0,
                                "codeSnippets": ["answer()"],
                                "blankValues": [],
                            }
                        ],
                        "starter": [],
                    }
                ),
                "demo.log": "[]",
            }
            element_html = (
                '<pl-faded-parsons answers-name="demo" format="no-code">'
                "<code-lines>kept()</code-lines>"
                "</pl-faded-parsons>"
            )

            with patch.object(pl_faded_parsons.pl, "get_uuid", return_value="uuid-123"):
                rendered = pl_faded_parsons.render(element_html, data)

        self.assertNotIn('id="starter-code-uuid-123"', rendered)
        self.assertNotIn('id="ol-starter-code-uuid-123"', rendered)

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
                rendered = pl_faded_parsons.render(element_html, data)

        self.assertIn('style="--pl-faded-parsons-indent: 1;"', rendered)

    def test_parse_compiles_solution_tray_and_submitted_file(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            tmp_path = Path(temp_dir)
            data = make_question_data(tmp_path)
            data["raw_submitted_answers"] = {
                "demo.main": json.dumps(
                    {
                        "solution": [
                            {
                                "indent": 1,
                                "codeSnippets": ["return ", ""],
                                "blankValues": ["value"],
                            }
                        ],
                        "starter": [
                            {
                                "indent": 0,
                                "codeSnippets": ["ignored()"],
                                "blankValues": [],
                            }
                        ],
                    }
                ),
                "demo.log": "[]",
            }

            element_html = (
                '<pl-faded-parsons answers-name="demo" file-name="student.py">'
                "</pl-faded-parsons>"
            )

            pl_faded_parsons.parse(element_html, data)

        self.assertEqual(data["submitted_answers"]["demo"], "    return value")
        self.assertEqual(
            base64.b64decode(data["submitted_answers"]["_files"]["student.py"]).decode(
                "utf-8"
            ),
            "    return value",
        )


if __name__ == "__main__":
    unittest.main()
