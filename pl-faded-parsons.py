from __future__ import annotations

import prairielearn as pl # type: ignore
import base64
import html as html_lib
import json
import random
import re
from pathlib import Path
from typing import Any, Literal, TypedDict

import chevron
import lxml.html as xml

REQUIRED_ATTRIBS = ["answers-name"]
OPTIONAL_ATTRIBS = [
    "format",
    "language",
    "file-name",
    "solution-path",
    "log",
    "max-indent-level",
    "enable-copy-code",
]

FORMAT_RIGHT = "right"
FORMAT_BOTTOM = "bottom"
FORMAT_ONE_TRAY = "one-tray"
FORMAT_NO_CODE = "no-code"
VALID_FORMATS = {FORMAT_RIGHT, FORMAT_BOTTOM, FORMAT_ONE_TRAY}

LINE_COMMENT_PREFIX = r"(?:#|//)"
COMMENT_START_PATTERN = re.compile(LINE_COMMENT_PREFIX)
PIN_PATTERN = re.compile(rf"{LINE_COMMENT_PREFIX}pin\b(?:\((\d+)\))?")
LEGACY_GIVEN_PATTERN = re.compile(rf"{LINE_COMMENT_PREFIX}(\d+)given\b")
DISTRACTOR_PATTERN = re.compile(rf"{LINE_COMMENT_PREFIX}distractor")
LEGACY_BLANK_SUFFIX_PATTERN = re.compile(
    rf"{LINE_COMMENT_PREFIX}blank\s*(.*?)(?={LINE_COMMENT_PREFIX}|\r?\n|$)"
)
MARKUP_BLANK_PATTERN = re.compile(r"\b__\((.*?)\)__\b|\b_{3,4}\b")
INDENT = "    "
DEBUG = False

class ParsingError(Exception):
    """Raised when saved widget state cannot be reconstructed."""


class SavedLine(TypedDict):
    """Serialized representation of one code line in the widget trays."""

    indent: int
    pinned: bool
    codeSnippets: list[str]
    blankValues: list[str]
    blankPlaceholders: list[str]


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
    enable_copy_code: bool
    markup: str
    pre_text: str
    post_text: str
    pre_text_indent: float
    post_text_indent: float
    visual_indent: int
    max_indent_level: int
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
        state = _load_state(config, data)
        params = _build_question_params(config, state)
    elif panel == "submission":
        state = _load_state(config, data)
        params = {
            "code": _compile_code(state["solution"]),
            "has_feedback": bool(data.get("feedback")),
            "incomplete_blank_message": _find_empty_blank_message(state["solution"]),
        }
    elif panel == "answer":
        params = {"solution_path": _require_solution_path(config)}
    else:
        raise ValueError(f"Invalid panel type: {panel}")

    return _render_template(f"pl-faded-parsons-{panel}.mustache", params)


def parse(element_html: str, data: pl.QuestionData) -> None:
    """Compile the student's solution tray into PrairieLearn outputs."""

    config = _build_config(element_html, data)
    state = _load_state(config, data)
    empty_blank_message = _find_empty_blank_message(state["solution"])
    if empty_blank_message is not None:
        data["format_errors"][config["answers_name"]] = empty_blank_message
        return

    student_code = _compile_code(state["solution"])

    if DEBUG:
        print("DEBUG parse answers_name:", config["answers_name"])
        print("DEBUG parse solution state:", state["solution"])
        print("DEBUG parse compiled student_code:", repr(student_code))

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
    raw_format_name = pl.get_string_attrib(element, "format", FORMAT_RIGHT)
    if raw_format_name == FORMAT_NO_CODE:
        raise ValueError(
            "format `no-code` has been renamed to `one-tray`; use `one-tray` instead."
        )
    format_name = (
        raw_format_name
    )
    if format_name not in VALID_FORMATS:
        raise ValueError(
            f"Unsupported format `{format_name}`. Expected one of: "
            f"{', '.join(sorted(VALID_FORMATS))}"
        )

    pre_text_element = _get_unique_child(element, "pre-text")
    post_text_element = _get_unique_child(element, "post-text")
    code_lines_element = _get_unique_child(element, "code-lines")
    has_text_blocks = pre_text_element is not None or post_text_element is not None

    if format_name != FORMAT_ONE_TRAY and has_text_blocks:
        raise ValueError(
            "pre-text and post-text are only supported in one-tray format."
        )
    if (
        format_name == FORMAT_ONE_TRAY
        and code_lines_element is None
        and has_text_blocks
    ):
        raise ValueError(
            "one-tray format requires an explicit <code-lines> child when pre-text or post-text is present."
        )

    if (
        format_name == FORMAT_ONE_TRAY
        and code_lines_element is not None
        and not (code_lines_element.text or "").strip()
    ):
        raise ValueError("one-tray format requires non-empty <code-lines> content.")

    pre_text_source = _extract_raw_child_html(element_html, "pre-text")
    if pre_text_source is None:
        pre_text_source = pre_text_element.text if pre_text_element is not None else ""
    pre_text, pre_text_indent = _build_text_block(
        pre_text_source,
        placement="pre",
    )
    post_text_source = _extract_raw_child_html(element_html, "post-text")
    if post_text_source is None:
        post_text_source = (
            post_text_element.text if post_text_element is not None else ""
        )
    post_text, post_text_indent = _build_text_block(
        post_text_source,
        placement="post",
    )

    max_indent_level = pl.get_integer_attrib(element, "max-indent-level", 5)
    if max_indent_level < 0:
        raise ValueError("Attribute `max-indent-level` must be nonnegative.")

    visual_indent = (
        pl.get_integer_attrib(code_lines_element, "visual-indent", 0)
        if code_lines_element is not None
        else 0
    )
    if visual_indent < 0:
        raise ValueError("Attribute `visual-indent` must be nonnegative.")
    if format_name != FORMAT_ONE_TRAY and visual_indent:
        raise ValueError("visual-indent is only supported in one-tray format.")
    if format_name == FORMAT_ONE_TRAY and visual_indent and not has_text_blocks:
        raise ValueError(
            "visual-indent requires pre-text or post-text in one-tray format."
        )

    question_path = Path(data["options"]["question_path"])
    solution_path = question_path / pl.get_string_attrib(
        element, "solution-path", "./solution"
    )
    language = pl.get_string_attrib(element, "language", "")
    if language in ("py", "ipynb", "python") and not solution_path.exists():
        ans_path = question_path / "tests" / "ans.py"
        if ans_path.exists():
            solution_path = ans_path

    return {
        "answers_name": pl.get_string_attrib(element, "answers-name"),
        "format": format_name,
        "language": language,
        "file_name": pl.get_string_attrib(element, "file-name", "user_code.py"),
        "logging_enabled": pl.get_boolean_attrib(element, "log", False),
        "enable_copy_code": pl.get_boolean_attrib(
            element, "enable-copy-code", False
        ),
        "markup": _load_markup(
            element_html,
            element,
            question_path,
            code_lines_element,
            has_text_blocks=has_text_blocks,
        ),
        "pre_text": pre_text,
        "post_text": post_text,
        "pre_text_indent": pre_text_indent,
        "post_text_indent": post_text_indent,
        "visual_indent": visual_indent,
        "max_indent_level": max_indent_level,
        "size": "narrow" if format_name == FORMAT_RIGHT else "wide",
        "solution_path": solution_path,
    }


def _get_unique_child(
    element: xml.HtmlElement, tag: str
) -> xml.HtmlElement | None:
    """Return the single direct child with a given tag, if present."""

    matching_children = [child for child in element if child.tag == tag]
    if len(matching_children) > 1:
        raise ValueError(f"Only one <{tag}> child is allowed.")
    return matching_children[0] if matching_children else None


def _load_markup(
    element_html: str,
    element: xml.HtmlElement,
    question_path: Path,
    code_lines_element: xml.HtmlElement | None,
    *,
    has_text_blocks: bool,
) -> str:
    """Load author-provided code lines from the element or fallback file."""

    if code_lines_element is not None:
        raw_code_lines = _extract_raw_child_html(element_html, "code-lines")
        if raw_code_lines is not None:
            return html_lib.unescape(raw_code_lines)
        return code_lines_element.text or ""

    code_lines_path = question_path / "serverFilesQuestion" / "code_lines.txt"
    if code_lines_path.exists():
        return code_lines_path.read_text(encoding="utf-8")

    if not has_text_blocks:
        return _get_inner_html(element)

    return element.text or ""


def _extract_raw_child_html(element_html: str, tag: str) -> str | None:
    """Extract a child element's raw inner HTML from the source markup."""

    if isinstance(element_html, bytes):
        element_html = element_html.decode("utf-8")

    match = re.search(
        rf"<{tag}\b[^>]*>(.*?)</{tag}>",
        element_html,
        flags=re.DOTALL | re.IGNORECASE,
    )
    if match is None:
        return None
    return match.group(1)


def _get_inner_html(element: xml.HtmlElement) -> str:
    """Serialize the element's inner HTML without the outer wrapper."""

    parts: list[str] = []
    if element.text:
        parts.append(element.text)

    for child in element:
        parts.append(str(xml.tostring(child, encoding="unicode", method="html")))
        if child.tail:
            parts.append(child.tail)

    return "".join(parts)


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
    pinned = value.get("pinned", False)
    code_snippets = value.get("codeSnippets")
    blank_values = value.get("blankValues")
    blank_placeholders = value.get("blankPlaceholders")

    if not isinstance(indent, int):
        raise ParsingError("Line `indent` must be an integer.")
    if not isinstance(pinned, bool):
        raise ParsingError("Line `pinned` must be a boolean.")
    if not isinstance(code_snippets, list) or not all(
        isinstance(snippet, str) for snippet in code_snippets
    ):
        raise ParsingError("Line `codeSnippets` must be a list of strings.")
    if not isinstance(blank_values, list) or not all(
        isinstance(blank, str) for blank in blank_values
    ):
        raise ParsingError("Line `blankValues` must be a list of strings.")
    if blank_placeholders is None:
        blank_placeholders = blank_values
    if not isinstance(blank_placeholders, list) or not all(
        isinstance(blank, str) for blank in blank_placeholders
    ):
        raise ParsingError("Line `blankPlaceholders` must be a list of strings.")
    if len(code_snippets) != len(blank_values) + 1:
        raise ParsingError(
            "Each line must have exactly one more code snippet than blank value."
        )
    if len(blank_placeholders) != len(blank_values):
        raise ParsingError(
            "Line `blankPlaceholders` must have the same length as `blankValues`."
        )

    return {
        "indent": indent,
        "pinned": pinned,
        "codeSnippets": code_snippets,
        "blankValues": blank_values,
        "blankPlaceholders": blank_placeholders,
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
    solution_lines: list[SavedLine] = []
    distractor_lines: list[SavedLine] = []

    for raw_line in config["markup"].strip().splitlines():
        line_text = raw_line.strip()
        if not line_text:
            continue
        line = _parse_markup_line(line_text)

        match = PIN_PATTERN.search(line_text) or LEGACY_GIVEN_PATTERN.search(line_text)
        if match:
            line["indent"] = int(match.group(1) or 0)
            line["pinned"] = True
            solution_lines.append(line)
        elif DISTRACTOR_PATTERN.search(line_text):
            distractor_lines.append(line)
        else:
            starter_lines.append(line)

    if config["format"] == FORMAT_ONE_TRAY and distractor_lines:
        raise ValueError("one-tray format does not allow distractor lines.")

    # Seed from the variant so repeated renders keep the same initial tray order.
    rng = random.Random(f"{data['variant_seed']}:{config['answers_name']}")
    starter_lines.extend(
        rng.sample(distractor_lines, k=len(distractor_lines))
    )
    rng.shuffle(starter_lines)

    if config["format"] == FORMAT_ONE_TRAY:
        return {
            "solution": solution_lines + starter_lines,
            "starter": [],
            "log": [],
        }

    return {
        "solution": solution_lines,
        "starter": starter_lines,
        "log": [],
    }


def _find_empty_blank_message(lines: list[SavedLine]) -> str | None:
    """Return a parse error message when any submitted blank is empty."""

    for line in lines:
        for blank in line["blankValues"]:
            if not blank.strip():
                return (
                    "Your answer has incomplete blanks. Fill in every blank before submitting."
                )
    return None


def _parse_markup_line(line_text: str) -> SavedLine:
    """Convert one author-authored markup line into the saved line schema."""

    comment_match = COMMENT_START_PATTERN.search(line_text)
    code_portion = (
        line_text[:comment_match.start()].rstrip()
        if comment_match
        else line_text.rstrip()
    )
    code_snippets: list[str] = []
    blank_values: list[str] = []
    blank_placeholders: list[str] = []

    last_end = 0
    for match in MARKUP_BLANK_PATTERN.finditer(code_portion):
        start, end = match.span()
        code_snippets.append(code_portion[last_end:start])
        blank_values.append("")
        blank_placeholders.append(match.group(1) or "")
        last_end = end

    code_snippets.append(code_portion[last_end:])

    for index, raw_blank in enumerate(LEGACY_BLANK_SUFFIX_PATTERN.findall(line_text)):
        if index >= len(blank_placeholders):
            raise ParsingError(
                f"Too many blank placeholders specified, \n"
                f"only {len(blank_placeholders)} blanks exist"
            )
        text = raw_blank.strip()
        if blank_placeholders[index] and text:
            raise ParsingError(
                f"Placeholder text for blank {index} set twice: \n"
                f"{blank_placeholders[index]} and {text}"
            )
        blank_placeholders[index] = text

    return {
        "indent": 0,
        "pinned": False,
        "codeSnippets": code_snippets,
        "blankValues": blank_values,
        "blankPlaceholders": blank_placeholders,
    }


def _build_question_params(
    config: ElementConfig, state: WidgetState
) -> dict[str, Any]:
    """Translate controller state into the Mustache structure."""

    return {
        "answers_name": config["answers_name"],
        "bottom_layout": config["format"] == FORMAT_BOTTOM,
        "language": config["language"],
        "max_indent_level": config["max_indent_level"],
        "borderless": not config["pre_text"] and not config["post_text"],
        "previous_log": json.dumps(state["log"] if config["logging_enabled"] else []),
        "logging_enabled": config["logging_enabled"],
        "enable_copy_code": config["enable_copy_code"],
        "uuid": pl.get_uuid(),
        "starter": _build_tray_params(
            state["starter"],
            config["language"],
            config["size"],
            visual_indent=config["visual_indent"],
            allow_empty=config["format"] == FORMAT_ONE_TRAY,
        ),
        "pre_text": _build_text_block_params(
            config["pre_text"],
            config["language"],
            config["pre_text_indent"],
            placement="pre",
        ),
        "pin": _build_tray_params(
            state["solution"],
            config["language"],
            config["size"],
            visual_indent=config["visual_indent"],
            allow_empty=False,
        ),
        "post_text": _build_text_block_params(
            config["post_text"],
            config["language"],
            config["post_text_indent"],
            placement="post",
        ),
        "visual_indent": config["visual_indent"],
    }


def _build_tray_params(
    lines: list[SavedLine],
    language: str,
    size: str,
    *,
    visual_indent: int = 0,
    allow_empty: bool = False,
) -> dict[str, Any] | str:
    """Build the tray object expected by the Mustache question template."""

    if not lines and allow_empty:
        return ""

    tray = {
        "lines": [
            _line_to_mustache(line, language) for line in lines
        ],
        "narrow": size == "narrow",
        "wide": size == "wide",
        "visual_indent": visual_indent,
    }
    return tray


def _build_text_block(
    text: str, *, placement: Literal["pre", "post"]
) -> tuple[str, float]:
    """Normalize author-authored pre/post text and infer its indent."""

    if not text:
        return "", 0.0

    text = html_lib.unescape(text)
    expanded = text.expandtabs(4)
    lines = _trim_outer_blank_lines(expanded.splitlines())
    if not lines:
        return "", 0.0

    baseline_line = lines[0] if placement == "pre" else _find_last_nonempty_line(lines)
    indent_spaces = _infer_text_baseline_spaces(baseline_line)
    normalized_lines = [
        _normalize_text_block_line(line, indent_spaces, placement=placement, line_number=index + 1)
        for index, line in enumerate(lines)
    ]
    normalized = "\n".join(normalized_lines)
    if placement == "pre":
        normalized = normalized.rstrip("\n") + "\n"
    else:
        normalized = "\n" + normalized.lstrip("\n")
    return html_lib.escape(normalized), indent_spaces / 4


def _build_text_block_params(
    text: str,
    language: str,
    indent: float,
    *,
    placement: Literal["pre", "post"],
) -> dict[str, Any] | bool:
    """Return the Mustache payload for an optional pre/post text block."""

    if not text:
        return False

    return {"text": text, "language": language, "indent": indent}


def _trim_outer_blank_lines(lines: list[str]) -> list[str]:
    """Drop leading and trailing blank lines from a text block."""

    start = 0
    end = len(lines)

    while start < end and not lines[start].strip():
        start += 1
    while end > start and not lines[end - 1].strip():
        end -= 1

    return lines[start:end]


def _infer_text_baseline_spaces(line: str) -> int:
    """Infer the leading whitespace width from a baseline text line."""

    return len(line) - len(line.lstrip(" "))


def _find_last_nonempty_line(lines: list[str]) -> str:
    """Return the last non-empty line in a text block."""

    for line in reversed(lines):
        if line.strip():
            return line
    return ""


def _normalize_text_block_line(
    line: str,
    indent_spaces: int,
    *,
    placement: Literal["pre", "post"],
    line_number: int,
) -> str:
    """Validate and remove the shared leading whitespace prefix from one line."""

    if not line.strip():
        return ""

    prefix = " " * indent_spaces
    if indent_spaces and not line.startswith(prefix):
        raise IndentationError(
            f"{placement}-text line {line_number} does not match the leading whitespace prefix "
            "established by the baseline line."
        )
    return line[len(prefix):] if prefix else line


def _line_to_mustache(
    line: SavedLine, language: str
) -> dict[str, Any]:
    """Convert a saved line into the segment structure used by the template."""

    segments = []
    for index, part in enumerate(_interleave(line["codeSnippets"], line["blankValues"])):
        if part is None:
            continue
        if index % 2 == 0:
            segments.append({"code": {"content": part, "language": language}})
        else:
            placeholder = line["blankPlaceholders"][index // 2]
            segments.append(
                {
                    "blank": {
                        "value": part,
                        "placeholder": placeholder,
                        "width": max(4, len(part), len(placeholder)) + 1,
                    }
                }
            )

    return {
        "indent": line["indent"],
        "pinned": line.get("pinned", False),
        "segments": segments,
    }


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
            '\tEither:\n'
            f' - Provide an answer at {solution_path}\n'
            '  - Set the language to python and provide a tests/ans.py file\n'
            '  - Set "showCorrectAnswer" to false in `./info.json`'
        )
    return str(solution_path)


def _render_template(template_name: str, params: dict[str, Any]) -> str:
    """Render an element template from the local element tree."""

    template_path = Path(template_name)
    with template_path.open(encoding="utf-8") as template_file:
        return chevron.render(
            template_file,
            params,
            partials_path=template_path.parent
        ).strip()
