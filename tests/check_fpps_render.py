#!/usr/bin/env python3

from __future__ import annotations

import argparse
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


def _render_element(element_html: str, question_dir: Path) -> str:
    try:
        rendered = render_question_html(
            element_html,
            data_overrides={
                "options": {"question_path": str(question_dir)},
            },
            question_dir=question_dir,
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


def _question_root() -> Path:
    return Path(os.environ.get(QUESTION_ROOT_ENV, DEFAULT_QUESTION_ROOT)).resolve()


def pytest_generate_tests(metafunc: pytest.Metafunc) -> None:
    if "question_file" not in metafunc.fixturenames:
        return

    root = _question_root()
    question_files = _find_question_files(root)
    if not question_files:
        raise pytest.UsageError(
            f"No question files containing <pl-faded-parsons> were found under {root}."
        )

    metafunc.parametrize(
        "question_file",
        question_files,
        ids=[str(path.relative_to(root)) for path in question_files],
    )


def test_question_file_renders(question_file: Path) -> None:
    source = question_file.read_text(encoding="utf-8")
    elements = _extract_element_html(source)
    if not elements:
        pytest.fail(
            f"{question_file} did not contain any <pl-faded-parsons> elements."
        )

    for element_html in elements:
        _render_element(element_html, question_file.parent)


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
            "Render every pl-faded-parsons element found under a directory using "
            "the current Python implementation."
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
