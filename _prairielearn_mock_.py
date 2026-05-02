from typing import Any, Literal, Optional, TypedDict
from uuid import uuid4

import lxml.html


class PartialScore(TypedDict):
    score: float | None
    weight: Optional[int]
    feedback: Optional[str | dict[str, str] | Any]


class QuestionData(TypedDict):
    params: dict[str, Any]
    correct_answers: dict[str, Any]
    submitted_answers: dict[str, Any]
    format_errors: dict[str, Any]
    partial_scores: dict[str, PartialScore]
    score: float
    feedback: dict[str, Any]
    variant_seed: str
    options: dict[str, Any]
    raw_submitted_answers: dict[str, Any]
    editable: bool
    panel: Literal["question", "submission", "answer"]
    extensions: dict[str, Any]
    num_valid_submissions: int
    manual_grading: bool
    answers_names: dict[str, bool]


def get_string_attrib(element: lxml.html.HtmlElement, name: str, default: str | None = None) -> str:
    out = element.get(name, default)
    if out is None: raise ValueError()
    return out


def get_integer_attrib(
    element: lxml.html.HtmlElement, name: str, default: int = 0
) -> int:
    """Parse an integer HTML attribute using PrairieLearn-style semantics."""

    raw_value = element.get(name)
    if raw_value is None:
        return default

    try:
        return int(raw_value)
    except ValueError as exc:
        raise ValueError(
            f"Attribute `{name}` must be an integer, got `{raw_value}`."
        ) from exc


def get_boolean_attrib(
    element: lxml.html.HtmlElement, name: str, default: bool = False
) -> bool:
    """Parse a boolean HTML attribute using a small PrairieLearn-friendly vocabulary."""

    raw_value = element.get(name)
    if raw_value is None:
        return default

    normalized = raw_value.strip().lower()
    if normalized in {"true", "1", "yes", "on"}:
        return True
    if normalized in {"false", "0", "no", "off"}:
        return False

    raise ValueError(
        f"Attribute `{name}` must be a boolean string like `true` or `false`, got `{raw_value}`."
    )


def check_attribs(
    element: lxml.html.HtmlElement,
    required_attribs: list[str] | None = None,
    optional_attribs: list[str] | None = None,
) -> None:
    required = set(required_attribs or [])
    optional = set(optional_attribs or [])

    missing = [name for name in required if not element.get(name)]
    if missing:
        raise ValueError(f"Missing required attributes: {missing}")

    allowed = required | optional
    extra = sorted(set(element.attrib) - allowed)
    if extra:
        raise ValueError(f"Unexpected attributes: {extra}")


def check_answers_names(data: QuestionData, name: str | None) -> None:
    if not name:
        raise ValueError("answers-name is required")
    if data["answers_names"].get(name):
        raise ValueError(f"Duplicate answers-name: {name}")
    data["answers_names"][name] = True


def get_uuid() -> str:
    return str(uuid4())


def add_submitted_file(data: QuestionData, filename: str, contents: str) -> None:
    submitted_files = data["submitted_answers"].setdefault("_files", {})
    submitted_files[filename] = contents
