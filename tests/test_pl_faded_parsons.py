import base64
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

        self.sample_patch = patch.object(
            pl_faded_parsons.random, "sample", side_effect=lambda seq, k: list(seq)[:k]
        )
        self.shuffle_patch = patch.object(
            pl_faded_parsons.random, "shuffle", side_effect=lambda seq: None
        )
        self.sample_patch.start()
        self.shuffle_patch.start()
        self.addCleanup(self.sample_patch.stop)
        self.addCleanup(self.shuffle_patch.stop)

    def test_prepare_registers_answers_name(self):
        pl_faded_parsons.prepare(
            '<pl-faded-parsons answers-name="demo"></pl-faded-parsons>',
            self.data,
        )

        self.assertEqual(self.data["answers_names"], {"demo": True})

    def test_problem_parses_markup_into_trays_and_supports_blank_defaults(self):
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

        problem = pl_faded_parsons.FadedParsonsProblem(html, self.data)

        self.assertEqual(problem.pre_text, "before()")
        self.assertEqual(problem.post_text, "after()")
        self.assertEqual(problem.size, "wide")
        self.assertEqual(problem.trays.starter[1].blankValues, ["42"])
        self.assertEqual(
            [pl_faded_parsons.submission_line_to_code(line) for line in problem.trays.solution],
            ["    given() "],
        )
        self.assertEqual(
            [pl_faded_parsons.submission_line_to_code(line) for line in problem.trays.starter],
            ["starter()", "value = 42 ", "ignored() "],
        )

    def test_problem_uses_prior_submission_when_present(self):
        self.data["raw_submitted_answers"] = {
            "demo.main": json.dumps(
                {
                    "solution": [
                        {"indent": 1, "codeSnippets": ["print(", ")"], "blankValues": ["x"]}
                    ],
                    "starter": [],
                }
            ),
            "demo.log": json.dumps(
                [{"timestamp": "2024-01-01T00:00:00Z", "tag": "move", "data": {"line": 1}}]
            ),
        }

        problem = pl_faded_parsons.FadedParsonsProblem(
            '<pl-faded-parsons answers-name="demo"></pl-faded-parsons>',
            self.data,
        )

        self.assertEqual(problem.to_code(), "    print(x)")
        self.assertEqual(problem.log[0].tag, "move")

    def test_right_format_rejects_pre_and_post_text(self):
        html = """
        <pl-faded-parsons answers-name="demo">
            <pre-text>not allowed</pre-text>
            <code-lines>pass</code-lines>
        </pl-faded-parsons>
        """

        with self.assertRaisesRegex(Exception, "pre-text and post-text are not supported"):
            pl_faded_parsons.FadedParsonsProblem(html, self.data)

    def test_render_question_includes_hidden_fields_and_text_blocks(self):
        self.data["panel"] = "question"
        html = """
        <pl-faded-parsons answers-name="demo" format="bottom" language="python">
            <pre-text>before()</pre-text>
            <code-lines>given() #0given
starter()</code-lines>
            <post-text>after()</post-text>
        </pl-faded-parsons>
        """

        with patch.object(pl_faded_parsons.pl, "get_uuid", return_value="uuid-123"):
            prev_cwd = os.getcwd()
            try:
                os.chdir(ELEMENT_DIR)
                rendered = pl_faded_parsons.render(html, self.data)
            finally:
                os.chdir(prev_cwd)

        self.assertIn('name="demo.main"', rendered)
        self.assertIn('value="[]"', rendered)
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

        prev_cwd = os.getcwd()
        try:
            os.chdir(ELEMENT_DIR)
            submission_rendered = pl_faded_parsons.render(html, submission_data)
            answer_rendered = pl_faded_parsons.render(
                html, make_question_data(self.tmp_path, panel="answer")
            )
        finally:
            os.chdir(prev_cwd)

        self.assertIn("<p>Submission:</p>", submission_rendered)
        self.assertIn("answer()", submission_rendered)
        self.assertIn("<p>The reference solution:</p>", answer_rendered)
        self.assertIn('source-file-name=', answer_rendered)
        self.assertIn(str(self.tmp_path), answer_rendered)
        self.assertIn("./solution", answer_rendered)

    def test_parse_writes_submission_file_and_legacy_fields(self):
        html = """
        <pl-faded-parsons answers-name="demo" file-name="student.py">
            <code-lines>print(!BLANK) #blank 7
return 3 #1given</code-lines>
        </pl-faded-parsons>
        """

        pl_faded_parsons.parse(html, self.data)

        expected_code = "    return 3 "
        self.assertEqual(self.data["submitted_answers"]["demo"], expected_code)
        self.assertEqual(
            self.data["submitted_answers"]["demostudent-parsons-solution"], "    "
        )
        self.assertEqual(
            self.data["submitted_answers"]["demosubmission-lines"][0]["content"],
            "    ",
        )
        self.assertEqual(
            self.data["submitted_answers"]["demostarter-lines"][0]["content"],
            "print(7) ",
        )

        encoded = self.data["submitted_answers"]["_files"]["student.py"]
        self.assertEqual(base64.b64decode(encoded).decode("ascii"), expected_code)

    def test_no_code_format_moves_starter_lines_into_solution(self):
        html = """
        <pl-faded-parsons answers-name="demo" format="no-code">
            <code-lines>given() #0given
starter()</code-lines>
        </pl-faded-parsons>
        """

        problem = pl_faded_parsons.FadedParsonsProblem(html, self.data)

        self.assertEqual(
            [pl_faded_parsons.submission_line_to_code(line) for line in problem.trays.solution],
            ["given() ", "starter()"],
        )
        self.assertEqual(problem.trays.starter, [])


if __name__ == "__main__":
    unittest.main()
