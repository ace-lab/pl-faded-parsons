#!/usr/bin/env python3

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path
from typing import NamedTuple

import lxml.html as xml
from lxml import etree
from browser.render_core import render_question_html


class RenderFailure(NamedTuple):
    question_file: Path
    element_index: int
    element_html: str
    error: str


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

    return [Path(line) for line in completed.stdout.splitlines() if line.strip()]


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


def check_directory(root: Path) -> int:
    question_files = _find_question_files(root)
    if not question_files:
        print(
            f"No question files containing <pl-faded-parsons> were found under {root}.",
            file=sys.stderr,
        )
        return 1

    rendered_count = 0
    failures: list[RenderFailure] = []
    for question_file in question_files:
        source = question_file.read_text(encoding="utf-8")
        for element_index, element_html in enumerate(_extract_element_html(source), start=1):
            try:
                _render_element(element_html, question_file.parent)
            except Exception as exc:
                failures.append(
                    RenderFailure(
                        question_file=question_file,
                        element_index=element_index,
                        element_html=element_html,
                        error=str(exc),
                    )
                )
                continue
            rendered_count += 1

    for failure in failures:
        print(
            f"{failure.question_file} [element {failure.element_index}]",
            file=sys.stderr,
        )
        print("element_html:", file=sys.stderr)
        print(failure.element_html, file=sys.stderr)
        print(failure.error, file=sys.stderr)

    print('summary')
    print(f"\n{rendered_count} success(es)")
    print(f"\n{len(failures)} failure(s)", file=sys.stderr if failures else sys.stdout)
    return int(bool(failures))


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

    return check_directory(root)


if __name__ == "__main__":
    raise SystemExit(main())
