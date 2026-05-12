from __future__ import annotations

from fppgen.__main__ import (
    _question_element_attrs_from_metadata,
    generate_question_html,
)


def test_metadata_attrs_are_translated_to_standard_element_attrs() -> None:
    attrs = _question_element_attrs_from_metadata(
        {
            "enable_copy_code": True,
            "language": "python",
            "max_optional_fades": 2,
            "blankDelimiter": "--",
        }
    )

    assert attrs == {
        "enable-copy-code": True,
        "language": "python",
        "max-optional-fades": 2,
    }


def test_question_html_includes_standard_attrs() -> None:
    rendered = generate_question_html(
        "print(__[DATA]__)",
        element_attrs={
            "enable_copy_code": True,
            "language": "python",
            "max_optional_fades": 2,
        }, # type: ignore
    )

    assert '<pl-faded-parsons answers-name="fpp"' in rendered
    assert 'enable-copy-code="true"' in rendered
    assert 'language="python"' in rendered
    assert 'max-optional-fades="2"' in rendered
    assert "blankDelimiter" not in rendered
