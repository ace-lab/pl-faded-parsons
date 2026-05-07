import base64
import importlib.util
import json
import re
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


ELEMENT_DIR = Path(__file__).resolve().parent.parent
BROWSER_DIR = ELEMENT_DIR / "tests" / "browser"
MODULE_PATH = ELEMENT_DIR / "pl-faded-parsons.py"

if str(ELEMENT_DIR) not in sys.path:
    sys.path.insert(0, str(ELEMENT_DIR))
if str(BROWSER_DIR) not in sys.path:
    sys.path.insert(0, str(BROWSER_DIR))

SPEC = importlib.util.spec_from_file_location("pl_faded_parsons", MODULE_PATH)
assert SPEC is not None
pl_faded_parsons = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(pl_faded_parsons)

from render_core import BANNED_IMPORT_GLOBALS, load_controller_module


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


def render_with_uuid(element_html: str, data: dict, uuid: str = "uuid-123") -> str:
    with patch.object(pl_faded_parsons.pl, "get_uuid", return_value=uuid):
        return pl_faded_parsons.render(element_html, data)


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

        with self.assertRaisesRegex(
            ValueError,
            "pre-text and post-text are only supported in one-tray format",
        ):
            pl_faded_parsons._build_config(html, self.data)

    def test_build_config_requires_code_lines_when_pre_or_post_text_present(self):
        html = """
        <pl-faded-parsons answers-name="demo" format="one-tray">
            <pre-text>before()</pre-text>
        </pl-faded-parsons>
        """

        with self.assertRaisesRegex(
            ValueError,
            "one-tray format requires an explicit <code-lines> child",
        ):
            pl_faded_parsons._build_config(html, self.data)

    def test_build_config_rejects_pre_and_post_text_outside_one_tray_format(self):
        html = """
        <pl-faded-parsons answers-name="demo" format="bottom">
            <pre-text>before()</pre-text>
            <code-lines>pass</code-lines>
            <post-text>after()</post-text>
        </pl-faded-parsons>
        """

        with self.assertRaisesRegex(
            ValueError,
            "pre-text and post-text are only supported in one-tray format",
        ):
            pl_faded_parsons._build_config(html, self.data)

    def test_build_config_requires_code_lines_in_one_tray_format(self):
        html = """
        <pl-faded-parsons answers-name="demo" format="one-tray">
            <pre-text>before()</pre-text>
        </pl-faded-parsons>
        """

        with self.assertRaisesRegex(
            ValueError,
            "one-tray format requires an explicit <code-lines> child",
        ):
            pl_faded_parsons._build_config(html, self.data)

    def test_build_config_allows_one_tray_without_code_lines_when_text_blocks_absent(self):
        html = '<pl-faded-parsons answers-name="demo" format="one-tray"></pl-faded-parsons>'

        config = pl_faded_parsons._build_config(html, self.data)
        state = pl_faded_parsons._build_initial_state(config, self.data)

        self.assertEqual(config["format"], "one-tray")
        self.assertEqual(config["markup"], "")
        self.assertEqual(state["solution"], [])
        self.assertEqual(state["starter"], [])

    def test_build_config_rejects_legacy_no_code_alias(self):
        html = '<pl-faded-parsons answers-name="demo" format="no-code"></pl-faded-parsons>'

        with self.assertRaisesRegex(
            ValueError,
            "format `no-code` has been renamed to `one-tray`",
        ):
            pl_faded_parsons._build_config(html, self.data)

    def test_build_config_uses_inner_html_when_code_lines_are_omitted(self):
        html = """
        <pl-faded-parsons answers-name="demo">
            given() #pin(1)
            starter()
        </pl-faded-parsons>
        """

        config = pl_faded_parsons._build_config(html, self.data)
        state = pl_faded_parsons._build_initial_state(config, self.data)

        self.assertIn("given() #pin(1)", config["markup"])
        self.assertEqual(
            [pl_faded_parsons._compile_line(line) for line in state["solution"]],
            ["    given()"],
        )
        self.assertEqual(
            [pl_faded_parsons._compile_line(line) for line in state["starter"]],
            ["starter()"],
        )

    def test_build_config_sanitizes_code_lines_inner_html(self):
        html = """
        <pl-faded-parsons answers-name="demo">
            <code-lines>
                <span>if a &amp; b &lt; c &gt; d</span>
            </code-lines>
        </pl-faded-parsons>
        """

        config = pl_faded_parsons._build_config(html, self.data)
        state = pl_faded_parsons._build_initial_state(config, self.data)

        self.assertIn("<span>if a & b < c > d</span>", config["markup"])
        self.assertEqual(
            [pl_faded_parsons._compile_line(line) for line in state["starter"]],
            ["<span>if a & b < c > d</span>"],
        )

    def test_build_config_preserves_literal_angle_brackets_in_code_lines(self):
        html = """
        <pl-faded-parsons answers-name="song" language="python">
          <code-lines>
              def __str__(self):
                return f"<Song> {super().desc()}"
          </code-lines>
        </pl-faded-parsons>
        """

        config = pl_faded_parsons._build_config(html, self.data)
        state = pl_faded_parsons._build_initial_state(config, self.data)

        self.assertIn('return f"<Song> {super().desc()}"', config["markup"])
        self.assertCountEqual(
            [pl_faded_parsons._compile_line(line) for line in state["starter"]],
            [
                "def __str__(self):",
                'return f"<Song> {super().desc()}"',
            ],
        )

    def test_build_config_strips_parser_inserted_closing_tag_from_code_lines(self):
        html = """
        <pl-faded-parsons answers-name="song" language="python">
          <code-lines>def __str__(self):
            return f"<Song> {super().desc()}"</code-lines>
        </pl-faded-parsons>
        """

        config = pl_faded_parsons._build_config(html, self.data)

        self.assertNotIn("</song>", config["markup"].lower())
        self.assertIn("<Song>", config["markup"])

    def test_build_config_preserves_nested_xml_markup_in_code_lines(self):
        html = """
        <pl-faded-parsons answers-name="demo" language="xml">
          <code-lines>
              <root>
                <child attr="1">text</child>
              </root>
          </code-lines>
        </pl-faded-parsons>
        """

        config = pl_faded_parsons._build_config(html, self.data)
        state = pl_faded_parsons._build_initial_state(config, self.data)

        self.assertIn("<root>", config["markup"])
        self.assertIn('<child attr="1">text</child>', config["markup"])
        self.assertCountEqual(
            [pl_faded_parsons._compile_line(line) for line in state["starter"]],
            ["<root>", '<child attr="1">text</child>', "</root>"],
        )

    def test_build_config_accepts_bytes_input_for_code_lines(self):
        html = (
            b'<pl-faded-parsons answers-name="demo">'
            b"<code-lines>print(&lt;Song&gt;)</code-lines>"
            b"</pl-faded-parsons>"
        )

        config = pl_faded_parsons._build_config(html, self.data)

        self.assertIn("print(<Song>)", config["markup"])

    def test_render_question_preserves_song_case_in_complex_python_example(self):
        html = """
        <pl-faded-parsons answers-name="song" language="python">
          <code-lines>
            @dataclass(frozen=True)
            class Song(___):
              title: str
              __(song length)__: float
              def __str__(self):
                return f"<Song> {super().desc()}"
          </code-lines>
        </pl-faded-parsons>
        """

        rendered = render_with_uuid(html, self.data)

        self.assertIn("&lt;Song&gt;", rendered)
        self.assertNotIn("&lt;song&gt;", rendered)

    def test_render_question_escapes_xml_code_lines_with_placeholder_blank_attributes(self):
        html = """
        <pl-faded-parsons answers-name="demo" language="xml">
            <code-lines><song attr="__(name)__">x</song></code-lines>
        </pl-faded-parsons>
        """

        rendered = render_with_uuid(html, self.data)

        self.assertIn('&lt;song attr=&quot;', rendered)
        self.assertIn('&quot;&gt;x&lt;/song&gt;', rendered)
        self.assertNotIn('<song attr=', rendered)
        self.assertNotIn('</song>', rendered)

    def test_render_question_escapes_xml_code_lines_with_blank_attributes(self):
        html = """
        <pl-faded-parsons answers-name="demo" language="xml">
            <code-lines><song attr="___">x</song></code-lines>
        </pl-faded-parsons>
        """

        rendered = render_with_uuid(html, self.data)

        self.assertIn('&lt;song attr=&quot;', rendered)
        self.assertIn('&quot;&gt;x&lt;/song&gt;', rendered)
        self.assertNotIn('<song attr=', rendered)
        self.assertNotIn('</song>', rendered)

    def test_render_question_escapes_xml_code_lines_with_blank_attributes_names(self):
        html = """
        <pl-faded-parsons answers-name="demo" language="xml">
            <code-lines><song ___="attr">x</song></code-lines>
        </pl-faded-parsons>
        """

        rendered = render_with_uuid(html, self.data)

        self.assertIn('&lt;song', rendered)
        self.assertIn('&quot;attr&quot;&gt;x&lt;/song&gt;', rendered)
        self.assertNotIn('<song', rendered)
        self.assertNotIn('="attr"', rendered)
        self.assertNotIn('</song>', rendered)

    def test_render_question_escapes_xml_code_lines_with_placeholder_blank_attributes_names(self):
        html = """
        <pl-faded-parsons answers-name="demo" language="xml">
            <code-lines><song __(name)__="attr">x</song></code-lines>
        </pl-faded-parsons>
        """

        rendered = render_with_uuid(html, self.data)

        self.assertIn('&lt;song', rendered)
        self.assertIn('&quot;attr&quot;&gt;x&lt;/song&gt;', rendered)
        self.assertNotIn('<song', rendered)
        self.assertNotIn('="attr"', rendered)
        self.assertNotIn('</song>', rendered)

    def test_build_config_rejects_duplicate_child_tags(self):
        html = """
        <pl-faded-parsons answers-name="demo" format="one-tray">
            <code-lines>first()</code-lines>
            <code-lines>second()</code-lines>
        </pl-faded-parsons>
        """

        with self.assertRaisesRegex(ValueError, "Only one <code-lines> child is allowed"):
            pl_faded_parsons._build_config(html, self.data)

    def test_build_initial_state_parses_givens_blanks_and_distractors(self):
        html = """
        <pl-faded-parsons answers-name="demo" format="bottom" language="python">
            <code-lines>given() #pin(1)
starter()
value = __(42)__
ignored() #distractor</code-lines>
        </pl-faded-parsons>
        """

        config = pl_faded_parsons._build_config(html, self.data)
        state = pl_faded_parsons._build_initial_state(config, self.data)

        self.assertEqual(config["size"], "wide")
        self.assertEqual(
            [pl_faded_parsons._compile_line(line) for line in state["solution"]],
            ["    given()"],
        )
        self.assertEqual(
            [pl_faded_parsons._compile_line(line) for line in state["starter"]],
            ["value = ", "ignored()", "starter()"],
        )
        self.assertEqual(state["starter"][0]["blankValues"], [""])
        self.assertEqual(state["starter"][0]["blankPlaceholders"], ["42"])

    def test_build_initial_state_accepts_legacy_given_marker(self):
        html = """
        <pl-faded-parsons answers-name="demo" language="python">
            <code-lines>legacy() #0given</code-lines>
        </pl-faded-parsons>
        """

        config = pl_faded_parsons._build_config(html, self.data)
        state = pl_faded_parsons._build_initial_state(config, self.data)

        self.assertEqual(
            [pl_faded_parsons._compile_line(line) for line in state["solution"]],
            ["legacy()"],
        )
        self.assertTrue(state["solution"][0]["pinned"])

    def test_build_initial_state_accepts_pin_without_suffix_as_zero_indent(self):
        html = """
        <pl-faded-parsons answers-name="demo" language="python">
            <code-lines>top() #pin</code-lines>
        </pl-faded-parsons>
        """

        config = pl_faded_parsons._build_config(html, self.data)
        state = pl_faded_parsons._build_initial_state(config, self.data)

        self.assertEqual(
            [pl_faded_parsons._compile_line(line) for line in state["solution"]],
            ["top()"],
        )
        self.assertEqual(state["solution"][0]["indent"], 0)
        self.assertTrue(state["solution"][0]["pinned"])

    def test_build_initial_state_ignores_pinned_comment_text(self):
        html = """
        <pl-faded-parsons answers-name="demo" language="python">
            <code-lines>line() #pinned</code-lines>
        </pl-faded-parsons>
        """

        config = pl_faded_parsons._build_config(html, self.data)
        state = pl_faded_parsons._build_initial_state(config, self.data)

        self.assertEqual(state["solution"], [])
        self.assertEqual(
            [pl_faded_parsons._compile_line(line) for line in state["starter"]],
            ["line()"],
        )

    def test_build_initial_state_accepts_c_style_comment_markers(self):
        html = """
        <pl-faded-parsons answers-name="demo" language="javascript">
            <code-lines>kept() //pin(1)
starter()
ignored() //distractor</code-lines>
        </pl-faded-parsons>
        """

        config = pl_faded_parsons._build_config(html, self.data)
        state = pl_faded_parsons._build_initial_state(config, self.data)

        self.assertEqual(
            [pl_faded_parsons._compile_line(line) for line in state["solution"]],
            ["    kept()"],
        )
        self.assertCountEqual(
            [pl_faded_parsons._compile_line(line) for line in state["starter"]],
            ["starter()", "ignored()"],
        )

    def test_build_initial_state_handles_empty_markup(self):
        html = '<pl-faded-parsons answers-name="demo"></pl-faded-parsons>'

        config = pl_faded_parsons._build_config(html, self.data)
        state = pl_faded_parsons._build_initial_state(config, self.data)

        self.assertEqual(state["solution"], [])
        self.assertEqual(state["starter"], [])
        self.assertEqual(state["log"], [])

    def test_parse_saved_state_preserves_pinned_flags(self):
        raw_main = json.dumps(
            {
                "solution": [
                    {
                        "indent": 0,
                        "pinned": True,
                        "codeSnippets": ["pinned()"],
                        "blankValues": [],
                    }
                ],
                "starter": [],
            }
        )

        state = pl_faded_parsons._parse_saved_state(raw_main, "[]")

        self.assertTrue(state["solution"][0]["pinned"])
        self.assertEqual(state["solution"][0]["codeSnippets"], ["pinned()"])

    def test_build_initial_state_moves_all_lines_into_solution_in_one_tray_mode(self):
        html = """
        <pl-faded-parsons answers-name="demo" format="one-tray">
            <code-lines>kept()
starter()
value = ___
</code-lines>
        </pl-faded-parsons>
        """

        config = pl_faded_parsons._build_config(html, self.data)
        state = pl_faded_parsons._build_initial_state(config, self.data)

        self.assertCountEqual(
            [pl_faded_parsons._compile_line(line) for line in state["solution"]],
            ["kept()", "starter()", "value = "],
        )
        self.assertEqual(state["starter"], [])

    def test_build_initial_state_rejects_distractors_in_one_tray_mode(self):
        html = """
        <pl-faded-parsons answers-name="demo" format="one-tray">
            <code-lines>kept()
ignored() #distractor
</code-lines>
        </pl-faded-parsons>
        """

        config = pl_faded_parsons._build_config(html, self.data)

        with self.assertRaisesRegex(
            ValueError,
            "one-tray format does not allow distractor lines",
        ):
            pl_faded_parsons._build_initial_state(config, self.data)

    def test_build_config_reads_visual_indent_from_code_lines(self):
        html = """
        <pl-faded-parsons answers-name="demo" format="one-tray">
            <pre-text>before()</pre-text>
            <code-lines visual-indent="2">kept()</code-lines>
            <post-text>after()</post-text>
        </pl-faded-parsons>
        """

        config = pl_faded_parsons._build_config(html, self.data)

        self.assertEqual(config["visual_indent"], 2)

    def test_build_config_reads_max_indent_level_from_element(self):
        html = """
        <pl-faded-parsons answers-name="demo" max-indent-level="7">
            <code-lines>kept()</code-lines>
        </pl-faded-parsons>
        """

        config = pl_faded_parsons._build_config(html, self.data)

        self.assertEqual(config["max_indent_level"], 7)

    def test_build_config_rejects_visual_indent_outside_one_tray_format(self):
        html = """
        <pl-faded-parsons answers-name="demo" format="bottom">
            <code-lines visual-indent="2">kept()</code-lines>
        </pl-faded-parsons>
        """

        with self.assertRaisesRegex(
            ValueError,
            "visual-indent is only supported in one-tray format",
        ):
            pl_faded_parsons._build_config(html, self.data)

    def test_build_config_rejects_visual_indent_without_pre_or_post_text(self):
        html = """
        <pl-faded-parsons answers-name="demo" format="one-tray">
            <code-lines visual-indent="2">kept()</code-lines>
        </pl-faded-parsons>
        """

        with self.assertRaisesRegex(
            ValueError,
            "visual-indent requires pre-text or post-text in one-tray format",
        ):
            pl_faded_parsons._build_config(html, self.data)

    def test_build_text_block_standardizes_pre_and_post_newlines(self):
        pre_text, pre_indent = pl_faded_parsons._build_text_block(
            "before()\nclass ListHelpers:\n  @staticmethod",
            placement="pre",
        )
        post_text, post_indent = pl_faded_parsons._build_text_block(
            "after()\nend",
            placement="post",
        )

        self.assertEqual(pre_text, "before()\nclass ListHelpers:\n  @staticmethod\n")
        self.assertEqual(post_text, "\nafter()\nend")
        self.assertEqual(pre_indent, 0)
        self.assertEqual(post_indent, 0)

    def test_build_text_block_expands_tabs_for_indent_inference(self):
        text, indent = pl_faded_parsons._build_text_block(
            "\t\tbefore()\n\t\t  helper()",
            placement="pre",
        )

        self.assertEqual(text, "before()\n  helper()\n")
        self.assertEqual(indent, 2.0)

    def test_build_text_block_uses_first_line_as_baseline_indent(self):
        text, indent = pl_faded_parsons._build_text_block(
            "        before()\n            helper()\n        tail()",
            placement="pre",
        )

        self.assertEqual(text, "before()\n    helper()\ntail()\n")
        self.assertEqual(indent, 2.0)

    def test_build_text_block_uses_last_line_as_post_baseline_indent(self):
        text, indent = pl_faded_parsons._build_text_block(
            "            before()\n        helper()\n    tail()",
            placement="post",
        )

        self.assertEqual(text, "\n        before()\n    helper()\ntail()")
        self.assertEqual(indent, 1.0)

    def test_build_text_block_params_returns_normalized_text(self):
        text, indent = pl_faded_parsons._build_text_block(
            "    before()\n        helper()",
            placement="pre",
        )
        params = pl_faded_parsons._build_text_block_params(
            text,
            "python",
            indent,
            placement="pre",
        )

        self.assertEqual(params["indent"], 1.0)
        self.assertEqual(params["text"], "before()\n    helper()\n")

    def test_build_text_block_rejects_inconsistent_leading_whitespace(self):
        with self.assertRaisesRegex(
            IndentationError,
            "pre-text line 2 does not match the leading whitespace prefix",
        ):
            pl_faded_parsons._build_text_block(
                "        before()\n  helper()",
                placement="pre",
            )

    def test_build_text_block_allows_zero_whitespace_at_block_start(self):
        text, indent = pl_faded_parsons._build_text_block(
            "before()\n    helper()",
            placement="pre",
        )

        self.assertEqual(text, "before()\n    helper()\n")
        self.assertEqual(indent, 0.0)

    def test_parse_markup_line_supports_multiple_blanks_and_empty_defaults(self):
        line = pl_faded_parsons._parse_markup_line(
            "print(___, ___) #blank first #blank"
        )

        self.assertEqual(line["codeSnippets"], ["print(", ", ", ")"])
        self.assertEqual(line["blankValues"], ["", ""])
        self.assertEqual(line["blankPlaceholders"], ["first", ""])

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

    def test_parse_saved_state_accepts_empty_trays_and_blank_values(self):
        state = pl_faded_parsons._parse_saved_state(
            json.dumps(
                {
                    "solution": [
                        {
                            "indent": 0,
                            "codeSnippets": ["value = ", ""],
                            "blankValues": [""],
                        }
                    ],
                    "starter": [],
                }
            ),
            "[]",
        )

        self.assertEqual(state["solution"][0]["blankValues"], [""])
        self.assertEqual(state["starter"], [])
        self.assertEqual(state["log"], [])

    def test_line_to_mustache_preserves_segments(self):
        line = {
            "indent": 1,
            "codeSnippets": ["print(", ")"],
            "blankValues": ["value"],
            "blankPlaceholders": ["hint"],
        }

        rendered = pl_faded_parsons._line_to_mustache(line, "python")

        self.assertEqual(rendered["indent"], 1)
        self.assertEqual(len(rendered["segments"]), 3)
        self.assertEqual(rendered["segments"][0]["code"]["content"], "print(")
        self.assertEqual(rendered["segments"][1]["blank"]["value"], "value")
        self.assertEqual(rendered["segments"][1]["blank"]["placeholder"], "hint")
        self.assertEqual(rendered["segments"][1]["blank"]["width"], 6)
        self.assertEqual(rendered["segments"][2]["code"]["content"], ")")

    def test_render_question_does_not_mark_missing_blank_inputs_on_first_load(self):
        html = """
        <pl-faded-parsons answers-name="demo" language="python">
            <code-lines>print(___) #blank</code-lines>
        </pl-faded-parsons>
        """

        rendered = render_with_uuid(html, self.data)

        self.assertNotIn("parsons-blank-missing", rendered)
        self.assertNotIn('aria-invalid="true"', rendered)
        self.assertIn('placeholder=""', rendered)
        self.assertIn('value=""', rendered)

    def test_render_question_preserves_blank_placeholder_without_setting_a_value(self):
        html = """
        <pl-faded-parsons answers-name="demo" language="python">
            <code-lines>print(___) #blank value</code-lines>
        </pl-faded-parsons>
        """

        rendered = render_with_uuid(html, self.data)

        self.assertIn('placeholder="value"', rendered)
        self.assertIn('value=""', rendered)
        self.assertNotIn('value="value"', rendered)

    def test_render_question_includes_hidden_fields_and_text_blocks(self):
        html = """
        <pl-faded-parsons answers-name="demo" format="one-tray" language="python">
            <pre-text>    before()
        class ListHelpers:
            @staticmethod</pre-text>
            <code-lines>given()</code-lines>
            <post-text>    after()
end</post-text>
        </pl-faded-parsons>
        """

        rendered = render_with_uuid(html, self.data)

        self.assertIn('name="demo.main"', rendered)
        self.assertIn('name="demo.log"', rendered)
        self.assertIn("before()", rendered)
        self.assertIn("after()", rendered)
        self.assertIn('class="pre-text-wrapper"', rendered)
        self.assertIn('class="post-text-wrapper"', rendered)
        self.assertIn('class="prettyprint pre-text"', rendered)
        self.assertIn('class="prettyprint post-text"', rendered)
        self.assertIn("maxIndentLevel: 5,", rendered)
        self.assertIn("visualIndent: 0,", rendered)
        self.assertIn('class="pre-text-wrapper"', rendered)
        self.assertIn('class="post-text-wrapper"', rendered)

    def test_render_question_preserves_literal_xml_in_pre_text(self):
        html = """
        <pl-faded-parsons answers-name="demo" format="one-tray" language="xml">
            <pre-text>
                <root attr="1">hello</root>
            </pre-text>
            <code-lines>given()</code-lines>
        </pl-faded-parsons>
        """

        rendered = render_with_uuid(html, self.data)

        self.assertIn("&lt;root attr=&quot;1&quot;&gt;hello&lt;/root&gt;", rendered)
        self.assertNotIn("<root attr=\"1\">", rendered)
        self.assertNotIn("</root>", rendered)

    def test_render_question_preserves_literal_xml_in_post_text(self):
        html = """
        <pl-faded-parsons answers-name="demo" format="one-tray" language="xml">
            <code-lines>given()</code-lines>
            <post-text>
                <root attr="1">goodbye</root>
            </post-text>
        </pl-faded-parsons>
        """

        rendered = render_with_uuid(html, self.data)

        self.assertIn("&lt;root attr=&quot;1&quot;&gt;goodbye&lt;/root&gt;", rendered)
        self.assertNotIn("<root attr=\"1\">", rendered)
        self.assertNotIn("</root>", rendered)

    def test_render_question_omits_copy_button_by_default(self):
        html = """
        <pl-faded-parsons answers-name="demo" language="python">
            <code-lines>given()</code-lines>
        </pl-faded-parsons>
        """

        rendered = render_with_uuid(html, self.data)

        self.assertNotIn('class="widget-copy', rendered)
        self.assertNotIn('aria-label="copy to clipboard"', rendered)

    def test_render_question_includes_copy_button_when_enabled(self):
        html = """
        <pl-faded-parsons answers-name="demo" language="python" enable-copy-code="true">
            <code-lines>given()</code-lines>
        </pl-faded-parsons>
        """

        rendered = render_with_uuid(html, self.data)

        self.assertIn("widget-controls-uuid-123", rendered)
        self.assertIn('class="widget-copy btn btn-light border d-flex align-items-center"', rendered)

    def test_render_question_omits_outer_border_in_borderless_one_tray_mode(self):
        html = """
        <pl-faded-parsons answers-name="demo" format="one-tray" language="python">
            <code-lines>given()</code-lines>
        </pl-faded-parsons>
        """

        rendered = render_with_uuid(html, self.data)

        self.assertIn("pl-faded-parsons-borderless", rendered)
        self.assertNotIn("fpp-tray-corner-label-solution", rendered)

    def test_render_question_keeps_outer_border_when_one_tray_mode_has_text(self):
        html = """
        <pl-faded-parsons answers-name="demo" format="one-tray" language="python">
            <pre-text>before()</pre-text>
            <code-lines>given()</code-lines>
        </pl-faded-parsons>
        """

        rendered = render_with_uuid(html, self.data)

        self.assertNotIn("pl-faded-parsons-borderless", rendered)

    def test_render_question_is_borderless_when_no_pre_or_post_text_in_right_mode(self):
        html = """
        <pl-faded-parsons answers-name="demo" language="python">
            <code-lines>given()</code-lines>
        </pl-faded-parsons>
        """

        rendered = render_with_uuid(html, self.data)

        self.assertIn("pl-faded-parsons-borderless", rendered)

    def test_render_question_threads_visual_indent_into_trays(self):
        html = """
        <pl-faded-parsons answers-name="demo" format="one-tray">
            <pre-text>before()</pre-text>
            <code-lines visual-indent="3">kept()</code-lines>
            <post-text>after()</post-text>
        </pl-faded-parsons>
        """

        rendered = render_with_uuid(html, self.data)

        self.assertIn("visualIndent: 3,", rendered)

    def test_render_question_threads_max_indent_level_into_widget_config(self):
        html = """
        <pl-faded-parsons answers-name="demo" max-indent-level="7">
            <code-lines>given()</code-lines>
        </pl-faded-parsons>
        """

        rendered = render_with_uuid(html, self.data)

        self.assertIn("maxIndentLevel: 7,", rendered)

    def test_render_question_makes_widget_root_the_tab_stop(self):
        html = """
        <pl-faded-parsons answers-name="demo" format="bottom" language="python">
            <code-lines>print(___) #blank 7
starter()</code-lines>
        </pl-faded-parsons>
        """
        rendered = render_with_uuid(html, self.data)

        self.assertRegex(
            rendered,
            re.compile(r'id="pl-faded-parsons-uuid-123"\s+role="application"\s+tabindex="0"'),
        )
        self.assertRegex(
            rendered,
            re.compile(r'tabindex="-1"\s+aria-grabbed="false"'),
        )
        self.assertRegex(
            rendered,
            re.compile(r'class="parsons-blank"\s+tabindex="-1"'),
        )
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

        self.assertIn("SUBMISSION", submission_rendered)
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

        self.assertIn("SUBMISSION", rendered)
        self.assertNotIn("FEEDBACK", rendered)

    def test_submission_panel_shows_incomplete_blank_feedback(self):
        html = '<pl-faded-parsons answers-name="demo"></pl-faded-parsons>'

        submission_data = make_question_data(self.tmp_path, panel="submission")
        submission_data["raw_submitted_answers"] = {
            "demo.main": json.dumps(
                {
                    "solution": [
                        {
                            "indent": 0,
                            "codeSnippets": ["print(", ")"],
                            "blankValues": [""],
                        }
                    ],
                    "starter": [],
                }
            )
        }

        rendered = pl_faded_parsons.render(html, submission_data)

        self.assertIn("Your answer has incomplete blanks.", rendered)
        self.assertIn('class="alert alert-danger"', rendered)
        self.assertIn("TEST-HOOK:INCOMPLETE-BLANKS", rendered)

    def test_render_respects_logging_toggle_and_one_tray_layout(self):
        html = """
        <pl-faded-parsons answers-name="demo" log="true" format="one-tray">
            <code-lines>print("hello")</code-lines>
        </pl-faded-parsons>
        """

        data = make_question_data(self.tmp_path)
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

        rendered = render_with_uuid(html, data)

        self.assertIn("loggingEnabled: true", rendered)
        self.assertNotIn('id="starter-code-uuid-123"', rendered)
        self.assertIn('id="solution-uuid-123"', rendered)
        self.assertIn("problemOpened", rendered)

    def test_parse_writes_submission_file_using_answers_name_only(self):
        html = """
        <pl-faded-parsons answers-name="demo" file-name="student.py">
            <code-lines>print(___) #blank 7
return 3 #pin(1)</code-lines>
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

    def test_parse_writes_empty_solution_to_file(self):
        html = '<pl-faded-parsons answers-name="demo" file-name="student.py"></pl-faded-parsons>'

        pl_faded_parsons.parse(html, self.data)

        self.assertEqual(self.data["submitted_answers"]["demo"], "")
        self.assertEqual(
            base64.b64decode(self.data["submitted_answers"]["_files"]["student.py"]).decode(
                "utf-8"
            ),
            "",
        )

    def test_parse_reports_empty_blanks_as_format_errors(self):
        html = """
        <pl-faded-parsons answers-name="demo" file-name="student.py">
            <code-lines>print(___) #blank</code-lines>
        </pl-faded-parsons>
        """

        self.data["raw_submitted_answers"] = {
            "demo.main": json.dumps(
                {
                    "solution": [
                        {
                            "indent": 0,
                            "codeSnippets": ["print(", ")"],
                            "blankValues": [""],
                        }
                    ],
                    "starter": [],
                }
            ),
            "demo.log": "[]",
        }

        pl_faded_parsons.parse(html, self.data)

        self.assertEqual(
            self.data["format_errors"]["demo"],
            "Your answer has incomplete blanks. Fill in every blank before submitting.",
        )
        self.assertNotIn("demo", self.data["submitted_answers"])
        self.assertNotIn("_files", self.data["submitted_answers"])

    def test_one_tray_format_moves_starter_lines_into_solution(self):
        html = """
        <pl-faded-parsons answers-name="demo" format="one-tray">
            <code-lines>given() #pin
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

    def test_browser_loader_omits_prairielearn_import_metadata(self):
        controller = load_controller_module()

        for banned_name in BANNED_IMPORT_GLOBALS:
            self.assertNotIn(banned_name, vars(controller))

        self.assertTrue(hasattr(controller, "prepare"))
        self.assertTrue(hasattr(controller, "render"))
        self.assertTrue(hasattr(controller, "parse"))


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

    def test_render_hides_empty_starter_tray_in_one_tray_format(self):
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
                '<pl-faded-parsons answers-name="demo" format="one-tray">'
                "<code-lines>kept()</code-lines>"
                "</pl-faded-parsons>"
            )

            with patch.object(pl_faded_parsons.pl, "get_uuid", return_value="uuid-123"):
                rendered = pl_faded_parsons.render(element_html, data)

        self.assertNotIn('id="starter-code-uuid-123"', rendered)
        self.assertNotIn('id="ol-starter-code-uuid-123"', rendered)

    def test_render_rejects_legacy_no_code_format(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            tmp_path = Path(temp_dir)
            data = make_question_data(tmp_path)
            element_html = '<pl-faded-parsons answers-name="demo" format="no-code"></pl-faded-parsons>'

            with patch.object(pl_faded_parsons.pl, "get_uuid", return_value="uuid-123"):
                with self.assertRaisesRegex(
                    ValueError,
                    "format `no-code` has been renamed to `one-tray`",
                ):
                    pl_faded_parsons.render(element_html, data)

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
