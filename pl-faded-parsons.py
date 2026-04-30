"""PrairieLearn controller for the `pl-faded-parsons` element.

The company asked for this controller to center on PrairieLearn's lifecycle
methods instead of a large object model. This module keeps that contract
explicit:

- `prepare()` validates element usage.
- `render()` rebuilds the UI state for the requested panel.
- `parse()` compiles the student's solution tray into source code.

The browser widget persists raw UI state in two hidden inputs:

- `<answers-name>.main` stores the trays.
- `<answers-name>.log` stores the event log.

Those JSON payloads are intentionally passed around as plain dictionaries and
lists so the Python, Mustache, and JavaScript layers all speak the same shape.
"""

from __future__ import annotations

try:
    import prairielearn as pl
except ModuleNotFoundError:
    import _prairielearn_mock_ as pl

import base64
import json
import random
import re
from pathlib import Path
from typing import Any, TypedDict

import chevron
import lxml.html as xml


REQUIRED_ATTRIBS = ["answers-name"]
OPTIONAL_ATTRIBS = ["format", "language", "file-name", "solution-path", "log"]

FORMAT_RIGHT = "right"
FORMAT_BOTTOM = "bottom"
FORMAT_NO_CODE = "no-code"
VALID_FORMATS = {FORMAT_RIGHT, FORMAT_BOTTOM, FORMAT_NO_CODE}

GIVEN_PATTERN = re.compile(r"#(\d+)given")
DISTRACTOR_PATTERN = re.compile(r"#distractor")
BLANK_PATTERN = re.compile(r"#blank [^#]*")
INDENT = "    "
MAX_DISTRACTORS = 10


class ParsingError(Exception):
    """Raised when saved widget state cannot be reconstructed."""


class SavedLine(TypedDict):
    """Serialized representation of one code line in the widget trays."""

    indent: int
    codeSnippets: list[str]
    blankValues: list[str]


class LogEntry(TypedDict):
    """Serialized interaction log entry emitted by the browser widget."""

    timestamp: str
    tag: str
    data: dict[str, Any]


class WidgetState(TypedDict):
    """Saved tray state exchanged between PrairieLearn and the browser."""

    solution: list[SavedLine]
    starter: list[SavedLine]
    log: list[LogEntry]


class ElementConfig(TypedDict):
    """Element configuration derived from the author-authored markup."""

    answers_name: str
    format: str
    language: str
    file_name: str
    logging_enabled: bool
    markup: str
    pre_text: str
    post_text: str
    size: str
    solution_path: Path


def prepare(element_html: str, data: pl.QuestionData) -> None:
    """Validate the element and reserve its PrairieLearn answers-name."""

    element = _parse_element(element_html)
    answers_name = pl.get_string_attrib(element, "answers-name")
    pl.check_answers_names(data, answers_name)


def render(element_html: str, data: pl.QuestionData) -> str:
    """Render the element for the current PrairieLearn panel."""

    config = _build_config(element_html, data)
    panel = data["panel"]

    if panel == "question":
        params = _build_question_params(config, _load_state(config, data))
    elif panel == "submission":
        params = {
            "code": _compile_code(_load_state(config, data)["solution"]),
            "has_feedback": bool(data.get("feedback")),
        }
    elif panel == "answer":
        params = {"solution_path": _require_solution_path(config)}
    else:
        raise ValueError(f"Invalid panel type: {panel}")

    return _render_template(f"pl-faded-parsons-{panel}.mustache", params)


def parse(element_html: str, data: pl.QuestionData) -> None:
    """Compile the student's solution tray into PrairieLearn outputs."""

    config = _build_config(element_html, data)
    student_code = _compile_code(_load_state(config, data)["solution"])

    data["submitted_answers"][config["answers_name"]] = student_code
    pl.add_submitted_file(
        data,
        config["file_name"],
        base64.b64encode(student_code.encode("utf-8")).decode("ascii"),
    )


def _parse_element(element_html: str) -> xml.HtmlElement:
    """Parse the element markup and validate supported attributes."""

    element = xml.fragment_fromstring(element_html)
    pl.check_attribs(
        element,
        required_attribs=REQUIRED_ATTRIBS,
        optional_attribs=OPTIONAL_ATTRIBS,
    )
    return element


def _build_config(element_html: str, data: pl.QuestionData) -> ElementConfig:
    """Collect the element configuration needed across the lifecycle."""

    element = _parse_element(element_html)
    format_name = pl.get_string_attrib(element, "format", FORMAT_RIGHT)
    if format_name not in VALID_FORMATS:
        raise ValueError(
            f"Unsupported format `{format_name}`. Expected one of: "
            f"{', '.join(sorted(VALID_FORMATS))}"
        )

    pre_text = _get_child_text(element, "pre-text").strip("\n")
    post_text = _get_child_text(element, "post-text").strip("\n")
    if format_name == FORMAT_RIGHT and (pre_text or post_text):
        raise ValueError(
            "pre-text and post-text are not supported in right mode. "
            'Use `format="bottom"` or `format="no-code"` instead.'
        )

    question_path = Path(data["options"]["question_path"])
    solution_path = question_path / pl.get_string_attrib(
        element, "solution-path", "./solution"
    )

    return {
        "answers_name": pl.get_string_attrib(element, "answers-name"),
        "format": format_name,
        "language": pl.get_string_attrib(element, "language", ""),
        "file_name": pl.get_string_attrib(element, "file-name", "user_code.py"),
        "logging_enabled": pl.get_boolean_attrib(element, "log", False),
        "markup": _load_markup(element, question_path),
        "pre_text": pre_text,
        "post_text": post_text,
        "size": "narrow" if format_name == FORMAT_RIGHT else "wide",
        "solution_path": solution_path,
    }


def _get_child_text(element: xml.HtmlElement, tag: str) -> str:
    """Return the direct text content for a named child tag."""

    for child in element:
        if child.tag == tag:
            return child.text or ""
    return ""


def _load_markup(element: xml.HtmlElement, question_path: Path) -> str:
    """Load author-provided code lines from the element or fallback file."""

    markup = _get_child_text(element, "code-lines")
    if markup:
        return markup

    code_lines_path = question_path / "serverFilesQuestion" / "code_lines.txt"
    if code_lines_path.exists():
        return code_lines_path.read_text(encoding="utf-8")

    return element.text or ""


def _load_state(config: ElementConfig, data: pl.QuestionData) -> WidgetState:
    """Load saved widget state when present, otherwise build the initial trays."""

    raw_answers = data["raw_submitted_answers"]
    main_key = f"{config['answers_name']}.main"

    if raw_answers.get(main_key):
        return _parse_saved_state(
            raw_answers[main_key],
            raw_answers.get(f"{config['answers_name']}.log", "[]"),
        )

    return _build_initial_state(config, data)


def _parse_saved_state(raw_main: str, raw_log: str) -> WidgetState:
    """Validate the widget JSON that PrairieLearn received from the browser."""

    main = json.loads(raw_main)
    if not isinstance(main, dict):
        raise ParsingError("Expected saved tray state to be a JSON object.")

    return {
        "solution": _parse_lines(main.get("solution"), "solution"),
        "starter": _parse_lines(main.get("starter", []), "starter"),
        "log": _parse_log(raw_log),
    }


def _parse_lines(value: Any, field_name: str) -> list[SavedLine]:
    """Validate a list of code lines from saved widget state."""

    if not isinstance(value, list):
        raise ParsingError(f"Expected `{field_name}` to be a list of lines.")

    return [_parse_line(line) for line in value]


def _parse_line(value: Any) -> SavedLine:
    """Validate one saved code line."""

    if not isinstance(value, dict):
        raise ParsingError("Expected each saved line to be a JSON object.")

    indent = value.get("indent")
    code_snippets = value.get("codeSnippets")
    blank_values = value.get("blankValues")

    if not isinstance(indent, int):
        raise ParsingError("Line `indent` must be an integer.")
    if not isinstance(code_snippets, list) or not all(
        isinstance(snippet, str) for snippet in code_snippets
    ):
        raise ParsingError("Line `codeSnippets` must be a list of strings.")
    if not isinstance(blank_values, list) or not all(
        isinstance(blank, str) for blank in blank_values
    ):
        raise ParsingError("Line `blankValues` must be a list of strings.")
    if len(code_snippets) != len(blank_values) + 1:
        raise ParsingError(
            "Each line must have exactly one more code snippet than blank value."
        )

    return {
        "indent": indent,
        "codeSnippets": code_snippets,
        "blankValues": blank_values,
    }


def _parse_log(raw_log: str) -> list[LogEntry]:
    """Validate the saved interaction log."""

    log_entries = json.loads(raw_log)
    if not isinstance(log_entries, list):
        raise ParsingError("Expected saved log data to be a JSON list.")

    parsed_log = []
    for entry in log_entries:
        if not isinstance(entry, dict):
            raise ParsingError("Each log entry must be a JSON object.")
        if not isinstance(entry.get("timestamp"), str):
            raise ParsingError("Log entry `timestamp` must be a string.")
        if not isinstance(entry.get("tag"), str):
            raise ParsingError("Log entry `tag` must be a string.")
        if not isinstance(entry.get("data"), dict):
            raise ParsingError("Log entry `data` must be an object.")
        parsed_log.append(
            {
                "timestamp": entry["timestamp"],
                "tag": entry["tag"],
                "data": entry["data"],
            }
        )

    return parsed_log


def _build_initial_state(
    config: ElementConfig, data: pl.QuestionData
) -> WidgetState:
    """Build the initial starter and solution trays from author markup."""

    starter_lines: list[SavedLine] = []
    given_lines: list[SavedLine] = []
    distractor_lines: list[SavedLine] = []

    for raw_line in config["markup"].strip().splitlines():
        line_text = raw_line.strip()
        line = _parse_markup_line(line_text)

        given_match = GIVEN_PATTERN.search(line_text)
        if given_match:
            line["indent"] = int(given_match.group(1))
            given_lines.append(line)
        elif DISTRACTOR_PATTERN.search(line_text):
            distractor_lines.append(line)
        else:
            starter_lines.append(line)

    # Seed from the variant so repeated renders keep the same initial tray order.
    rng = random.Random(f"{data['variant_seed']}:{config['answers_name']}")
    starter_lines.extend(
        rng.sample(distractor_lines, k=min(len(distractor_lines), MAX_DISTRACTORS))
    )
    rng.shuffle(starter_lines)

    if config["format"] == FORMAT_NO_CODE:
        return {
            "solution": given_lines + starter_lines,
            "starter": [],
            "log": [],
        }

    return {
        "solution": given_lines,
        "starter": starter_lines,
        "log": [],
    }


def _parse_markup_line(line_text: str) -> SavedLine:
    """Convert one author-authored markup line into the saved line schema."""

    code_portion = line_text.split("#", 1)[0].rstrip()
    code_snippets = code_portion.split("!BLANK")
    blank_values = [""] * (len(code_snippets) - 1)

    for index, raw_blank in enumerate(BLANK_PATTERN.findall(line_text)):
        if index >= len(blank_values):
            break
        blank_values[index] = raw_blank.replace("#blank", "", 1).strip()

    return {
        "indent": 0,
        "codeSnippets": code_snippets,
        "blankValues": blank_values,
    }


def _build_question_params(
    config: ElementConfig, state: WidgetState
) -> dict[str, Any]:
    """Translate controller state into the Mustache structure."""

    return {
        "answers_name": config["answers_name"],
        "language": config["language"],
        "previous_log": json.dumps(state["log"] if config["logging_enabled"] else []),
        "logging_enabled": config["logging_enabled"],
        "uuid": pl.get_uuid(),
        "starter": _build_tray_params(
            state["starter"],
            config["language"],
            config["size"],
            allow_empty=config["format"] == FORMAT_NO_CODE,
        ),
        "pre_text": _build_text_block(config["pre_text"], config["language"]),
        "given": _build_tray_params(
            state["solution"],
            config["language"],
            config["size"],
            allow_empty=False,
        ),
        "post_text": _build_text_block(config["post_text"], config["language"]),
    }


def _build_tray_params(
    lines: list[SavedLine],
    language: str,
    size: str,
    *,
    allow_empty: bool = False,
) -> dict[str, Any] | str:
    """Build the tray object expected by the Mustache question template."""

    if not lines and allow_empty:
        return ""

    tray = {
        "lines": [_line_to_mustache(line, language) for line in lines],
        "narrow": size == "narrow",
        "wide": size == "wide",
    }
    return tray


def _build_text_block(text: str, language: str) -> dict[str, str] | bool:
    """Return the optional pre/post text block for Mustache rendering."""

    if not text:
        return False
    return {"text": text, "language": language}


def _line_to_mustache(line: SavedLine, language: str) -> dict[str, Any]:
    """Convert a saved line into the segment structure used by the template."""

    segments = []
    for index, part in enumerate(_interleave(line["codeSnippets"], line["blankValues"])):
        if part is None:
            continue
        if index % 2 == 0:
            segments.append({"code": {"content": part, "language": language}})
        else:
            segments.append(
                {"blank": {"default": part, "width": max(4, len(part) + 1)}}
            )

    return {"indent": line["indent"], "segments": segments}


def _compile_code(lines: list[SavedLine]) -> str:
    """Compile the solution tray into the source code graders should consume."""

    return "\n".join(_compile_line(line) for line in lines)


def _compile_line(line: SavedLine) -> str:
    """Compile one saved line into source text."""

    return INDENT * line["indent"] + "".join(
        part for part in _interleave(line["codeSnippets"], line["blankValues"]) if part
    )


def _interleave(left: list[str], right: list[str]) -> list[str]:
    """Interleave snippet and blank lists while keeping their order stable."""

    merged: list[str] = []
    max_len = max(len(left), len(right))
    for index in range(max_len):
        if index < len(left):
            merged.append(left[index])
        if index < len(right):
            merged.append(right[index])
    return merged


def _require_solution_path(config: ElementConfig) -> str:
    """Return the reference solution path or raise a clear authoring error."""

    solution_path = config["solution_path"]
    if not solution_path.exists():
        raise FileNotFoundError(
            "\n"
            f"\tCorrect answer not found at `{solution_path}`!\n"
            '\tProvide an answer or set "showCorrectAnswer" to false in `./info.json`'
        )
    return str(solution_path)


def _render_template(template_name: str, params: dict[str, Any]) -> str:
    """Render an element template from this directory.

    Using absolute paths keeps the controller independent from the process
    working directory, which makes local tests and upstream integration simpler.
    """

    template_path = Path(template_name)
    with template_path.open(encoding="utf-8") as template_file:
        return chevron.render(
            template_file,
            params,
            partials_path=template_path.parent
        ).strip()
