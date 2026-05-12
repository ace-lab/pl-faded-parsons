from argparse import (
    ArgumentParser,
    BooleanOptionalAction,
    Namespace,
    RawTextHelpFormatter,
)
from pathlib import Path
from re import compile, Pattern

from lib.consts import Bcolors, PROGRAM_DESCRIPTION


def format_ln(source_path: Path | str | None, line_number: int):
    prefix = str(source_path) if source_path is not None else "line"
    return f'({prefix}:{line_number})'


def write_to(parent_dir: Path | str, file_path: Path | str, data: str):
    """Opens ./`parent_dir`/`file_path` and writes `data` to it"""
    (Path(parent_dir) / file_path).write_text(data, encoding='utf-8')


def make_if_absent(dir_path: Path):
    """Creates nested directories if they do not yet exist"""
    dir_path.mkdir(parents=True, exist_ok=True)


def read_region_source_lines(
    source_path: Path | str | None, region_source: Path | str
) -> str:
    """Reads the region_source and returns its contents, or raises
    a FileNotFoundError or other OSError in opening the file.

    Searches in ./ and ./`source_path`/ for `region_source`
    """
    region_source = Path(region_source)
    if source_path is not None and not region_source.exists():
        region_source = Path(source_path).parent / region_source

    if region_source.exists():
        return region_source.read_text()

    raise FileNotFoundError(str(region_source))


def auto_detect_sources(questions_dir: Path | None = None) -> list[Path]:
    if questions_dir is None:
        Bcolors.warn("** No paths provided, auto-detecting questions directory **")

        try:
            questions_dir = resolve_path("questions", path_is_dir=True, silent=True)
        except FileNotFoundError as e:
            Bcolors.fail(
                "** Auto-detection failed. Please provide paths to sources. (use --help for more info) **"
            )
            if e.args:
                Bcolors.fail(*e.args)
            raise

    return [
        f
        for f in Path(questions_dir).iterdir()
        if f.is_file() and f.suffix.endswith("py")
    ]


def resolve_path(
    path: Path | str,
    *,
    silent: bool = False,
    path_is_dir: bool = False,
) -> Path:
    """Attempts to find a matching source path in the following destinations:

    ```
    standard course directory structure:
    + <course>
    | ...        << search here 3rd
    |-+ elements/pl-faded-parsons
    | |-generate_fpp.py
    | | ...      << search here 1st
    |
    |-+ questions
    | | ...      << search here 2nd
    |
    ```
    Will search ./questions/ 4th, in case this is run from <course>/
    """
    path = Path(path)
    if not path_is_dir and (path.is_dir() or not path.suffix):
        path = path.with_suffix(".py")

    if path.exists():
        return path

    def warn():
        if not silent:
            Bcolors.warn(
                "- Could not find",
                original,
                "in current directory. Proceeding with detected file.",
            )

    original = path

    # if this is in 'elements/pl-faded-parsons', back up to course directory
    cwd = Path.cwd()
    if cwd.parent.name == "pl-faded-parsons" and cwd.parent.parent.name == "elements":
        # try original in a questions directory on the course level
        new_path = Path("..") / ".." / "questions" / original
        if new_path.exists():
            warn()
            return new_path

        # try original in course directory
        new_path = Path("..") / ".." / original
        if new_path.exists():
            warn()
            return new_path

    new_path = Path("questions") / original
    if new_path.exists():
        warn()
        return new_path

    raise FileNotFoundError(
        "Could not find " + ("directory " if path_is_dir else "file ") + str(original)
    )


def make_blank_re(config):
    """expects config to be
    `delim_str  | { "pattern": regex }  | { "start": str, "end": str }`
    """

    def validate(re_str: str) -> Pattern:
        if any(c in re_str for c in "#`'\""):
            raise SyntaxError(
                "custom patterns for blank delimiter " + "cannot use #, ', \", or `"
            )

        re = compile(re_str)

        if re.groups != 1:
            raise SyntaxError(
                "custom patterns for blankDelimiter must "
                + "capture exactly one group (the text to fade out)"
            )

        if re.match("") is not None:
            raise SyntaxError(
                "custom patterns for blankDelimiter must" + "not match the empty string"
            )

        return re

    reserved = r".+*?^$()[]{}|"

    def validate_l_r(left, right):
        if not left or not right:
            raise SyntaxError("blankDelimiter must not be empty")

        def esc(x):
            for c in reserved:
                if c == x:
                    return "\\" + c
            return x

        return validate(esc(left) + r"(.+?)" + esc(right))

    if isinstance(config, str):
        return validate_l_r(config, config)

    if not isinstance(config, dict):
        raise SyntaxError(
            "blankDelimiter metadata must either be a "
            + "delimiter string or a config object"
        )

    if "pattern" in config:
        return validate(config["pattern"])

    if "start" in config and "end" in config:
        s, e = config["start"], config["end"]

        if not isinstance(s, str) or not isinstance(e, str):
            raise SyntaxError(
                "custom blank delimiter start and end " + "must be strings"
            )

        return validate_l_r(s, e)

    raise SyntaxError("""blankDelimiter must be a string or adhere to schema:
    { "start": start_delimiter_string, "end": end_delimiter_string } |
    { "pattern": regex_string_that_captures_faded_text }""")


def parse_args(arg_text: str | None = None) -> Namespace:
    """Returns a Namespace containing all the flag and path data.
    If arg_text is not provided, uses `sys.argv`.
    """
    parser = ArgumentParser(
        description=PROGRAM_DESCRIPTION, formatter_class=RawTextHelpFormatter
    )

    parser.add_argument(
        "--profile", action="store_true", help="prints profile data after running"
    )
    parser.add_argument(
        "--verbosity",
        "-v",
        action="count",
        default=1,
        help="specify the verbosity with which to run (max 3)",
    )
    parser.add_argument(
        "--quiet",
        "-q",
        action="count",
        default=0,
        help="specify the reduction in verbosity with which to run (max 3)",
    )
    parser.add_argument(
        "--parse",
        action=BooleanOptionalAction,
        help="parse the code with py.ast to derive content (also --no-parse)",
    )
    parser.add_argument(
        "--make-dir",
        "--duplicate-directory",
        action=BooleanOptionalAction,
        default=True,
        help="create a directory with the name of the question in the output path",
    )
    parser.add_argument(
        "--output-path",
        "-o",
        action="store",
        nargs="?",
        metavar="path",
        type=Path,
        help="specify what directory to write the generated question to (see --duplicate-directory)\n"
        + "default is next to the source path",
    )
    parser.add_argument(
        "source_paths", action="append", nargs="*", metavar="paths", type=Path
    )
    parser.add_argument(
        "--questions-dir",
        action="append",
        metavar="path",
        type=Path,
        help="target all .py files in directory as sources",
    )
    parser.add_argument(
        "--force-json",
        action="append",
        metavar="path",
        type=Path,
        help="will overwrite the question's info.json file with auto-generated content",
    )

    # if arg_text is not set, then it gets from the command line
    ns = parser.parse_intermixed_args(args=arg_text)

    # unpack weird nesting, delete confusing name
    ns.source_paths = [p for lst in (ns.source_paths or []) for p in lst]

    # combine verbose-ness and quiet-ness and cut off into domain [-3, 3]
    ns.verbosity = ns.verbosity - ns.quiet
    ns.verbosity = min(ns.verbosity, 3)
    ns.verbosity = max(-3, ns.verbosity)

    if ns.questions_dir:
        for qd in ns.questions_dir:
            ns.source_paths.extend(auto_detect_sources(qd))

    ns.force_json = ns.force_json or list()
    return ns
