#!/usr/bin/env python3
"""Check that `pl-faded-parsons` elements render correctly.

Use this file in one of two ways:

1. Run it as a script and pass the root directory that contains question HTML
   files. The script finds every file with a ``<pl-faded-parsons>`` element and
   runs this test module against them.
2. Run it with `pytest` to execute the render checks directly.

Example:

    python check_fpps_render.py path/to/questions
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest
import lxml.html as xml
import lxml.etree as etree

from browser.render_core import render_question_html

ELEMENT_DIR = Path(__file__).resolve().parent.parent
DEFAULT_QUESTION_ROOT = ELEMENT_DIR.parent.parent / "questions"
QUESTION_ROOT_ENV = "PL_FPP_QUESTION_ROOT"


def _find_question_files(root: Path) -> list[Path]:
    pattern = "<pl-faded-parsons\\b"

    try:
        completed = subprocess.run(
            [
                "rg",
                "-l",
                "--glob",
                "*.html",
                pattern,
                str(root),
            ],
            capture_output=True,
            text=True,
            check=False,
        )
    except FileNotFoundError:
        return [
            path
            for path in sorted(root.rglob("*.html"))
            if "<pl-faded-parsons" in path.read_text(encoding="utf-8")
        ]

    if completed.returncode not in {0, 1}:
        raise RuntimeError(
            "rg failed while searching for pl-faded-parsons question files:\n"
            f"{completed.stderr.strip()}"
        )

    return sorted(Path(line) for line in completed.stdout.splitlines() if line.strip())


def _extract_element_html(source: str) -> list[str]:
    document = xml.document_fromstring(source)
    elements = document.xpath("//pl-faded-parsons")
    return [
        etree.tostring(element, encoding="unicode", method="html")
        for element in elements
    ]


def _render_element(
    element_html: str,
    question_dir: Path,
    *,
    panel: str = "question",
) -> str:
    try:
        rendered = render_question_html(
            element_html,
            data_overrides={
                "options": {"question_path": str(question_dir)},
            },
            question_dir=question_dir,
            panel=panel,
        )
    except Exception as exc:
        raise RuntimeError(
            "Failed to render a pl-faded-parsons block.\n"
            f"question_dir: {question_dir}\n"
            f"element_html:\n{element_html}\n"
            f"{exc}"
        ) from exc

    if "<pl-faded-parsons" in rendered:
        raise RuntimeError(
            "Render output still contains the source tag instead of generated HTML."
        )
    return rendered


def _should_render_submission_panel(question_dir: Path) -> bool:
    info_path = question_dir / "info.json"
    if not info_path.exists():
        return True

    info = json.loads(info_path.read_text(encoding="utf-8"))
    return info.get("showCorrectAnswer") is not False


def _question_root() -> Path:
    return Path(os.environ.get(QUESTION_ROOT_ENV, DEFAULT_QUESTION_ROOT)).resolve()


def pytest_generate_tests(metafunc: pytest.Metafunc) -> None:
    root = _question_root()
    question_files = _find_question_files(root)
    if not question_files:
        raise pytest.UsageError(
            f"No question files containing <pl-faded-parsons> were found under {root}."
        )

    if "question_file" in metafunc.fixturenames:
        metafunc.parametrize(
            "question_file",
            question_files,
            ids=[str(path.relative_to(root)) for path in question_files],
        )

    elif "submission_file" in metafunc.fixturenames:
        metafunc.parametrize(
            "question_file",
            [
                question_file
                for question_file in question_files
                if _should_render_submission_panel(question_file.parent)
            ],
            ids=[str(path.relative_to(root)) for path in question_files],
        )


def test_question_file_renders(question_file: Path) -> None:
    source = question_file.read_text(encoding="utf-8")
    elements = _extract_element_html(source)
    if not elements:
        pytest.fail(f"{question_file} did not contain any <pl-faded-parsons> elements.")

    for element_html in elements:
        assert _render_element(element_html, question_file.parent)


def test_submission_file_renders(question_file: Path) -> None:
    source = question_file.read_text(encoding="utf-8")
    elements = _extract_element_html(source)
    if not elements:
        pytest.fail(f"{question_file} did not contain any <pl-faded-parsons> elements.")

    for element_html in elements:
        assert 'pl-code' in _render_element(
            element_html,
            question_file.parent,
            panel="submission",
        )


def _run_pytest(root: Path) -> int:
    os.environ[QUESTION_ROOT_ENV] = str(root)
    return pytest.main(
        [
            str(Path(__file__).resolve()),
        ]
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Render every pl-faded-parsons element found in an html file "
            "under a directory using the current pl-faded-parsons implementation."
        )
    )
    parser.add_argument("directory", type=Path, help="root directory to scan")
    args = parser.parse_args(argv)

    root = args.directory.resolve()
    if not root.is_dir():
        parser.error(f"{root} is not a directory")

    if not _find_question_files(root):
        print(
            f"No question files containing <pl-faded-parsons> were found under {root}.",
            file=sys.stderr,
        )
        return 1

    return _run_pytest(root)


if __name__ == "__main__":
    raise SystemExit(main())
