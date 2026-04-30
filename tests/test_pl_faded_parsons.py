import base64
import importlib.util
import json
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


def make_question_data(tmp_path: Path, *, panel: str = "question") -> dict:
    solution_path = tmp_path / "solution"
    solution_path.write_text("expected_solution()\n", encoding="utf-8")
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
        "panel": panel,
        "extensions": {},
        "num_valid_submissions": 0,
        "manual_grading": False,
        "answers_names": {},
    }


class TestPlFadedParsonsController(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)
        self.tmp_path = Path(self.temp_dir.name)
        self.data = make_question_data(self.tmp_path)

    def test_prepare_registers_answers_name(self):
        pl_faded_parsons.prepare(
            '<pl-faded-parsons answers-name="demo"></pl-faded-parsons>',
            self.data,
        )

        self.assertEqual(self.data["answers_names"], {"demo": True})

    def test_prepare_requires_nonempty_answers_name(self):
        with self.assertRaisesRegex(ValueError, "Missing required attributes"):
            pl_faded_parsons.prepare(
                "<pl-faded-parsons></pl-faded-parsons>",
                self.data,
            )

        with self.assertRaisesRegex(ValueError, "Missing required attributes"):
            pl_faded_parsons.prepare(
                '<pl-faded-parsons answers-name=""></pl-faded-parsons>',
                self.data,
            )

    def test_prepare_requires_unique_answers_name(self):
        html = '<pl-faded-parsons answers-name="demo"></pl-faded-parsons>'

        pl_faded_parsons.prepare(html, self.data)

        with self.assertRaisesRegex(ValueError, "Duplicate answers-name: demo"):
            pl_faded_parsons.prepare(html, self.data)

    def test_build_config_rejects_pre_and_post_text_in_right_mode(self):
        html = """
        <pl-faded-parsons answers-name="demo">
            <pre-text>not allowed</pre-text>
            <code-lines>pass</code-lines>
        </pl-faded-parsons>
        """

        with self.assertRaisesRegex(ValueError, "pre-text and post-text are not supported"):
            pl_faded_parsons._build_config(html, self.data)

    def test_build_initial_state_parses_givens_blanks_and_distractors(self):
        html = """
        <pl-faded-parsons answers-name="demo" format="bottom" language="python">
            <pre-text>before()</pre-text>
            <code-lines>given() #1given
starter()
value = !BLANK #blank 42
ignored() #distractor</code-lines>
            <post-text>after()</post-text>
        </pl-faded-parsons>
        """

        config = pl_faded_parsons._build_config(html, self.data)
        state = pl_faded_parsons._build_initial_state(config, self.data)

        self.assertEqual(config["pre_text"], "before()")
        self.assertEqual(config["post_text"], "after()")
        self.assertEqual(config["size"], "wide")
        self.assertEqual(
            [pl_faded_parsons._compile_line(line) for line in state["solution"]],
            ["    given()"],
        )
        self.assertEqual(
            [pl_faded_parsons._compile_line(line) for line in state["starter"]],
            ["value = 42", "ignored()", "starter()"],
        )
        self.assertEqual(state["starter"][0]["blankValues"], ["42"])

    def test_parse_saved_state_validates_shape(self):
        with self.assertRaisesRegex(
            pl_faded_parsons.ParsingError,
            "one more code snippet than blank value",
        ):
            pl_faded_parsons._parse_saved_state(
                json.dumps(
                    {
                        "solution": [
                            {
                                "indent": 0,
                                "codeSnippets": ["print(", ")"],
                                "blankValues": [],
                            }
                        ],
                        "starter": [],
                    }
                ),
                "[]",
            )

    def test_line_to_mustache_preserves_segments(self):
        line = {
            "indent": 1,
            "codeSnippets": ["print(", ")"],
            "blankValues": ["value"],
        }

        rendered = pl_faded_parsons._line_to_mustache(line, "python")

        self.assertEqual(rendered["indent"], 1)
        self.assertEqual(len(rendered["segments"]), 3)
        self.assertEqual(rendered["segments"][0]["code"]["content"], "print(")
        self.assertEqual(rendered["segments"][1]["blank"]["default"], "value")
        self.assertEqual(rendered["segments"][1]["blank"]["width"], 6)
        self.assertEqual(rendered["segments"][2]["code"]["content"], ")")

    def test_render_question_includes_hidden_fields_and_text_blocks(self):
        html = """
        <pl-faded-parsons answers-name="demo" format="bottom" language="python">
            <pre-text>before()</pre-text>
            <code-lines>given() #0given
starter()</code-lines>
            <post-text>after()</post-text>
        </pl-faded-parsons>
        """

        with patch.object(pl_faded_parsons.pl, "get_uuid", return_value="uuid-123"):
            rendered = pl_faded_parsons.render(html, self.data)

        self.assertIn('name="demo.main"', rendered)
        self.assertIn('name="demo.log"', rendered)
        self.assertIn("before()", rendered)
        self.assertIn("after()", rendered)
        self.assertIn("starter-code-uuid-123", rendered)
        self.assertIn("solution-uuid-123", rendered)

    def test_render_submission_and_answer_panels(self):
        html = '<pl-faded-parsons answers-name="demo"></pl-faded-parsons>'

        submission_data = make_question_data(self.tmp_path, panel="submission")
        submission_data["raw_submitted_answers"] = {
            "demo.main": json.dumps(
                {
                    "solution": [{"indent": 0, "codeSnippets": ["answer()"], "blankValues": []}],
                    "starter": [],
                }
            )
        }

        submission_rendered = pl_faded_parsons.render(html, submission_data)
        answer_rendered = pl_faded_parsons.render(
            html, make_question_data(self.tmp_path, panel="answer")
        )

        self.assertIn("<p>Submission:</p>", submission_rendered)
        self.assertIn("answer()", submission_rendered)
        self.assertIn("<p>The reference solution:</p>", answer_rendered)
        self.assertIn("source-file-name=", answer_rendered)
        self.assertIn(str(self.tmp_path / "solution"), answer_rendered)

    def test_submission_panel_hides_feedback_header_without_feedback(self):
        html = '<pl-faded-parsons answers-name="demo"></pl-faded-parsons>'

        submission_data = make_question_data(self.tmp_path, panel="submission")
        submission_data["raw_submitted_answers"] = {
            "demo.main": json.dumps(
                {
                    "solution": [{"indent": 0, "codeSnippets": ["answer()"], "blankValues": []}],
                    "starter": [],
                }
            )
        }

        rendered = pl_faded_parsons.render(html, submission_data)

        self.assertIn("<p>Submission:</p>", rendered)
        self.assertNotIn("Feedback", rendered)

    def test_parse_writes_submission_file_using_answers_name_only(self):
        html = """
        <pl-faded-parsons answers-name="demo" file-name="student.py">
            <code-lines>print(!BLANK) #blank 7
return 3 #1given</code-lines>
        </pl-faded-parsons>
        """

        pl_faded_parsons.parse(html, self.data)

        expected_code = "    return 3"
        self.assertEqual(self.data["submitted_answers"]["demo"], expected_code)
        self.assertNotIn("demostudent-parsons-solution", self.data["submitted_answers"])
        self.assertNotIn("demosubmission-lines", self.data["submitted_answers"])
        self.assertNotIn("demostarter-lines", self.data["submitted_answers"])
        self.assertEqual(
            base64.b64decode(self.data["submitted_answers"]["_files"]["student.py"]).decode(
                "utf-8"
            ),
            expected_code,
        )

    def test_no_code_format_moves_starter_lines_into_solution(self):
        html = """
        <pl-faded-parsons answers-name="demo" format="no-code">
            <code-lines>given() #0given
starter()</code-lines>
        </pl-faded-parsons>
        """

        config = pl_faded_parsons._build_config(html, self.data)
        state = pl_faded_parsons._build_initial_state(config, self.data)

        self.assertEqual(
            [pl_faded_parsons._compile_line(line) for line in state["solution"]],
            ["given()", "starter()"],
        )
        self.assertEqual(state["starter"], [])


if __name__ == "__main__":
    unittest.main()
