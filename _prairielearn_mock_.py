from typing import Any, Literal, TypedDict, Optional


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
    panel: Literal['question', 'submission', 'answer']
    extensions: dict[str, Any]
    num_valid_submissions: int
    manual_grading: bool
    answers_names: dict[str, bool]