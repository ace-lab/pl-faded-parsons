from __future__ import annotations

from dataclasses import dataclass, field
from json import dumps
from pathlib import Path
from textwrap import dedent
from unittest.mock import patch
from uuid import UUID

import pytest

from fppgen import __main__ as fppgen_main
from fppgen.__main__ import Options, generate_fpp_question


FIXED_UUID = UUID("00000000-0000-4000-8000-000000000000")
MOCK_SERVER = dedent(
    """\
    # mock server.py
    def generate(data):
        return data
    """
).strip("\n")
MOCK_TEST_SCAFFOLD = "# mock test scaffold"


@dataclass(frozen=True, slots=True)
class SmokeCase:
    name: str
    source_path: str
    source_text: str
    prompt_code: str
    answer_code: str
    setup_code: str
    question_text: str | None = None
    question_attrs: str = ""
    test_region: str = ""
    server_code: str = MOCK_SERVER
    info_json: str | None = None
    metadata_json: str | None = None
    import_files: dict[str, str] = field(default_factory=dict)


def qhtml(prompt_code: str, *, question_text: str | None = None, attrs: str = "") -> str:
    tab = "  "
    question_block = "" if question_text is None else question_text
    indented = prompt_code.replace("\n", "\n" + tab)
    return (
        "<!-- AUTO-GENERATED FILE -->\n"
        "<pl-question-panel>\n"
        f"{question_block}\n"
        "</pl-question-panel>\n\n"
        "<!-- see README for where the various parts of question live -->\n"
        f'<pl-faded-parsons answers-name="fpp"{attrs}>\n'
        f"{tab}{indented}\n"
        "</pl-faded-parsons>"
    )


def generated_info_json(title: str) -> str:
    return dumps(
        {
            "uuid": str(FIXED_UUID),
            "title": title,
            "topic": "",
            "tags": ["berkeley", "fp"],
            "type": "v3",
            "gradingMethod": "External",
            "externalGradingOptions": {
                "image": "mock/grader",
            },
        },
        indent=4,
    ) + "\n"


def metadata_json() -> str:
    return dumps(
        {
            "autograder": ".py",
            "parse": False,
            "make-dir": True,
            "output-path": "",
        }
    )


def build_expected_files(case: SmokeCase) -> dict[str, str]:
    qdir = Path(case.source_path).with_suffix("")
    expected = {
        str(qdir / "question.html"): qhtml(
            case.prompt_code,
            question_text=case.question_text,
            attrs=case.question_attrs,
        ),
        str(qdir / "server.py"): case.server_code,
        str(qdir / "solution"): case.answer_code,
        str(qdir / "tests" / "test.py"): case.test_region or MOCK_TEST_SCAFFOLD,
        str(qdir / "tests" / "ans.py"): case.answer_code,
        str(qdir / "tests" / "setup_code.py"): case.setup_code,
        str(qdir / "info.json"): case.info_json or generated_info_json(qdir.name.replace("_", " ").title()),
        str(qdir / "metadata.json"): case.metadata_json or metadata_json(),
    }

    return expected


def build_fake_fs(case: SmokeCase) -> dict[str, str]:
    source_path = Path(case.source_path)
    fake_fs = {str(source_path): case.source_text}
    for rel_path, contents in case.import_files.items():
        fake_fs[str(source_path.parent / rel_path)] = contents
    return fake_fs


def run_case(case: SmokeCase) -> tuple[dict[str, str], list[tuple[str, str]]]:
    writes: dict[str, str] = {}
    copy_calls: list[tuple[str, str]] = []
    fake_fs = build_fake_fs(case)

    def fake_exists(self: Path) -> bool:
        return str(self) in fake_fs

    def fake_read_text(self: Path, *args, **kwargs) -> str:
        try:
            return fake_fs[str(self)]
        except KeyError as exc:  # pragma: no cover - better failure message
            raise FileNotFoundError(str(self)) from exc

    def fake_resolve_path(path, *, silent=False, path_is_dir=False):
        return Path(path)

    def fake_write_to(parent_dir, file_path, data):
        writes[str(Path(parent_dir) / file_path)] = data

    def fake_copyfile(src, dst):
        copy_calls.append((str(src), str(dst)))

    class FakeAutograder:
        def info_json_update(self):
            return {
                "gradingMethod": "External",
                "externalGradingOptions": {
                    "image": "mock/grader",
                },
            }

        def generate_server(self, setup_code, answer_code, *, no_ast=False, tab="    "):
            return MOCK_SERVER, [], []

        def populate_tests_dir(
            self,
            test_dir,
            answer_code,
            setup_code,
            test_region,
            pre_code="",
            post_code="",
            log_details=True,
        ):
            fppgen_main.io_helpers.write_to(
                test_dir, "test.py", test_region or MOCK_TEST_SCAFFOLD
            )
            fppgen_main.io_helpers.write_to(test_dir, "ans.py", answer_code)
            fppgen_main.io_helpers.write_to(test_dir, "setup_code.py", setup_code)

        def clean_tests_dir(self, test_dir):
            return None

    with (
        patch.object(Path, "exists", fake_exists),
        patch.object(Path, "read_text", fake_read_text),
        patch.object(fppgen_main.io_helpers, "resolve_path", fake_resolve_path),
        patch.object(fppgen_main.io_helpers, "write_to", fake_write_to),
        patch.object(fppgen_main.io_helpers, "make_if_absent", lambda path: None),
        patch.object(fppgen_main, "copyfile", fake_copyfile),
        patch.object(fppgen_main, "new_autograder_from_ext", lambda ext: FakeAutograder()),
        patch.object(fppgen_main, "uuid4", lambda: FIXED_UUID),
    ):
        generate_fpp_question(
            Path(case.source_path),
            options=Options(
                profile=False,
                source_paths=[Path(case.source_path)],
                verbosity=-1,
                do_parse=False,
                make_dir=True,
            ),
        )

    return writes, copy_calls


CASES = [
    SmokeCase(
        name="simple_add",
        source_path="examples/simple_add.py",
        source_text=dedent(
            """\
            def add(a, b):
                return a + b
            ## setup_code ##
            # no setup needed
            ## setup_code ##
            """
        ).strip("\n"),
        prompt_code="def add(a, b):\n    return a + b",
        answer_code="def add(a, b):\n    return a + b",
        setup_code="# no setup needed",
    ),
    SmokeCase(
        name="docstring_question",
        source_path="examples/docstring_question.py",
        source_text=dedent(
            '''\
            """Add two numbers."""
            def add(a, b):
                return a + b
            ## setup_code ##
            # no setup needed
            ## setup_code ##
            '''
        ).strip("\n"),
        prompt_code="def add(a, b):\n    return a + b",
        answer_code="def add(a, b):\n    return a + b",
        setup_code="# no setup needed",
        question_text="Add two numbers.",
    ),
    SmokeCase(
        name="blank_placeholders",
        source_path="examples/blank_placeholders.py",
        source_text=dedent(
            """\
            def add(a, b):
                return ?a? + ?b?
            ## setup_code ##
            # no setup needed
            ## setup_code ##
            """
        ).strip("\n"),
        prompt_code="def add(a, b):\n    return ___ + ___",
        answer_code="def add(a, b):\n    return a + b",
        setup_code="# no setup needed",
    ),
    SmokeCase(
        name="pin_and_comments",
        source_path="examples/pin_and_comments.py",
        source_text=dedent(
            """\
            def clamp(x, lo, hi): #pin
                # keep x in range
                return ?x? if x < hi else hi #pin(1)
            ## setup_code ##
            # no setup needed
            ## setup_code ##
            """
        ).strip("\n"),
        prompt_code="def clamp(x, lo, hi): #pin\n    return ___ if x < hi else hi #pin(1)",
        answer_code="def clamp(x, lo, hi):\n    # keep x in range\n    return x if x < hi else hi",
        setup_code="# no setup needed",
    ),
    SmokeCase(
        name="metadata_attrs",
        source_path="examples/metadata_attrs.py",
        source_text=dedent(
            """\
            ## metadata ##
            {"enable_copy_code": true, "language": "python", "max_optional_fades": 2}
            ## metadata ##
            def square(x):
                return x * x
            ## setup_code ##
            # no setup needed
            ## setup_code ##
            """
        ).strip("\n"),
        prompt_code="def square(x):\n    return x * x",
        answer_code="def square(x):\n    return x * x",
        setup_code="# no setup needed",
        question_attrs=' enable-copy-code="true" max-optional-fades="2" language="python"',
        metadata_json=metadata_json(),
    ),
    SmokeCase(
        name="explicit_question_text",
        source_path="examples/explicit_question_text.py",
        source_text=dedent(
            """\
            ## question_text ##
            Write a helper that formats a greeting.
            ## question_text ##
            def greet(name):
                return f"Hello, {name}"
            ## setup_code ##
            # no setup needed
            ## setup_code ##
            """
        ).strip("\n"),
        prompt_code='def greet(name):\n    return f"Hello, {name}"',
        answer_code='def greet(name):\n    return f"Hello, {name}"',
        setup_code="# no setup needed",
        question_text="Write a helper that formats a greeting.",
    ),
    SmokeCase(
        name="setup_region",
        source_path="examples/setup_region.py",
        source_text=dedent(
            """\
            # combine the prefix and the name
            def format_name(name):
                return prefix + name
            ## setup_code ##
            prefix = "Dr. "
            ## setup_code ##
            """
        ).strip("\n"),
        prompt_code="def format_name(name):\n    return prefix + name",
        answer_code="# combine the prefix and the name\ndef format_name(name):\n    return prefix + name",
        setup_code='prefix = "Dr. "',
    ),
    SmokeCase(
        name="server_and_test_regions",
        source_path="examples/server_and_test_regions.py",
        source_text=dedent(
            """\
            def echo(value):
                return value
            ## setup_code ##
            # no setup needed
            ## setup_code ##
            ## server ##
            # custom server override
            def generate(data):
                data["custom"] = True
                return data
            ## server ##
            ## test ##
            print("smoke")
            ## test ##
            """
        ).strip("\n"),
        prompt_code="def echo(value):\n    return value",
        answer_code="def echo(value):\n    return value",
        setup_code="# no setup needed",
        test_region='print("smoke")',
        server_code=dedent(
            """\
            # custom server override
            def generate(data):
                data["custom"] = True
                return data
            """
        ).strip("\n"),
    ),
    SmokeCase(
        name="custom_info_json",
        source_path="examples/custom_info_json.py",
        source_text=dedent(
            """\
            def noop():
                return None
            ## setup_code ##
            # no setup needed
            ## setup_code ##
            ## info.json ##
            {"uuid": "12345678-1234-5678-1234-567812345678", "title": "Custom Info", "topic": "demo", "tags": [], "type": "v3"}
            ## info.json ##
            """
        ).strip("\n"),
        prompt_code="def noop():\n    return None",
        answer_code="def noop():\n    return None",
        setup_code="# no setup needed",
        info_json='{"uuid": "12345678-1234-5678-1234-567812345678", "title": "Custom Info", "topic": "demo", "tags": [], "type": "v3"}',
    ),
    SmokeCase(
        name="imported_setup",
        source_path="examples/imported_setup.py",
        source_text=dedent(
            """\
            def area(w, h):
                return w * h * factor
            ## import shared/setup.py as setup_code ##
            """
        ).strip("\n"),
        prompt_code="def area(w, h):\n    return w * h * factor",
        answer_code="def area(w, h):\n    return w * h * factor",
        setup_code="factor = 2",
        import_files={"shared/setup.py": "factor = 2"},
    ),
]


@pytest.mark.parametrize("case", CASES, ids=[case.name for case in CASES])
def test_fppgen_smoke_generates_expected_files(case: SmokeCase) -> None:
    writes, copy_calls = run_case(case)
    qdir = Path(case.source_path).with_suffix("")
    expected_copy = (case.source_path, str(qdir / "source.py"))

    assert copy_calls == [expected_copy]
    assert writes == build_expected_files(case)
