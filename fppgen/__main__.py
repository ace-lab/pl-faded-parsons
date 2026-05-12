from json import dumps
from html import escape
from pathlib import Path
from shutil import copyfile
from uuid import uuid4
from dataclasses import dataclass, replace
from argparse import Namespace

from lib import consts, io_helpers

from lib.consts import QuestionElementAttributes, Metadata
from lib.tokens import lex
from lib.name_visitor import AnnotatedName
from lib.autograde import AutograderConfig, new_autograder_from_ext
from lib.parse import parse_fpp_regions


@dataclass(slots=True, frozen=True)
class Options:
    profile: bool
    source_paths: list
    verbosity: int
    do_parse: bool
    make_dir: bool
    force_generate_json: bool = False
    ag_extension: str = ""
    cli_out_path: Path | None = None
    metadata_out_path: Path | None = None

    @staticmethod
    def build(cli_args: Namespace, metadata: Metadata = {}, force_json: bool = False) -> "Options":
        return Options(
            force_generate_json=force_json,
            profile=cli_args.profile,
            source_paths=cli_args.source_paths,
            verbosity=cli_args.verbosity,
            cli_out_path=cli_args.output_path,
            do_parse=cli_args.parse,
            make_dir=cli_args.make_dir,
        ).with_metadata(metadata)

    @property
    def out_path(self) -> Path | None:
        if value := self.cli_out_path or self.metadata_out_path:
            return Path(value)
        return None

    def with_metadata(self, metadata: Metadata) -> "Options":
        return self.with_(
            do_parse=metadata.get("parse", self.do_parse),
            ag_extension=metadata.get("autograder", self.ag_extension),
            make_dir=metadata.get("make-dir", self.make_dir),
            metadata_out_path=metadata.get("output-path", self.metadata_out_path),
        )

    def with_(self, **kwargs: str | int | bool | Path | None):
        return replace(self, **kwargs)

    def dump(self) -> str:
        """Produce a json dump of this object"""

        return dumps(
            {
                "autograder": self.ag_extension,
                "parse": self.do_parse,
                "make-dir": self.make_dir,
                "output-path": self.out_path or "",
            }
        )


def generate_question_html(
    prompt_code: str,
    *,
    question_text: str | None = None,
    tab: str = "  ",
    setup_names: list[AnnotatedName] | None = None,
    answer_names: list[AnnotatedName] | None = None,
    element_attrs: consts.QuestionElementAttributes | None = None,
) -> str:
    """Turn an extracted prompt string into a question html file body"""
    indented = prompt_code.replace("\n", "\n" + tab)
    attrs = _format_element_attrs(element_attrs)

    if question_text is None:
        question_text = tab + "<!-- Write the question prompt here -->"
    elif setup_names or answer_names:
        question_text = tab + "<h3> Prompt </h3>\n" + tab + question_text

        question_text += "\n\n<markdown>\n"

        def format_annotated_name(name: AnnotatedName) -> str:
            out = " - `" + name.id
            if name.annotation:
                out += ": " + name.annotation
            out += "`"
            if name.description:
                out += ", " + name.description
            return out

        if setup_names:
            question_text += "### Provided\n"
            question_text += "\n".join(map(format_annotated_name, setup_names))
            if answer_names:
                question_text += "\n\n"

        if answer_names:
            question_text += "### Required\n"
            question_text += "\n".join(map(format_annotated_name, answer_names))

        question_text += "\n</markdown>\n"

    return """<!-- AUTO-GENERATED FILE -->
<pl-question-panel>
{question_text}
</pl-question-panel>

<!-- see README for where the various parts of question live -->
<pl-faded-parsons answers-name="fpp"{attrs}>
{tab}{indented}
</pl-faded-parsons>""".format(
        question_text=question_text,
        tab=tab,
        indented=indented,
        attrs=attrs,
    )


def _format_element_attrs(
    element_attrs: QuestionElementAttributes | None = None,
) -> str:
    """Format standard pl-faded-parsons attributes for the question tag."""
    if not element_attrs:
        return ""

    pieces = []
    for attr_name in consts.QUESTION_ELEMENT_ATTRS:
        value = element_attrs.get(attr_name)
        if value is None:
            value = element_attrs.get(attr_name.replace("-", "_"))
        if value is None:
            continue
        if isinstance(value, bool):
            value = "true" if value else "false"
        pieces.append(f' {attr_name}="{escape(str(value), quote=True)}"')

    return "".join(pieces)


def _question_element_attrs_from_metadata(
    metadata: Metadata,
) -> QuestionElementAttributes:
    """Select metadata entries that belong on the pl-faded-parsons tag."""
    return QuestionElementAttributes(
        **{
            k: v
            for k in consts.QUESTION_ELEMENT_ATTRS
            # check for the skewer-case-key first, fallback to snake_case_key
            if (v := metadata.get(k, None) or metadata.get(k.replace("-", "_"), None))
            is not None
        }
    )


def generate_info_json(
    question_name: str, autograder: AutograderConfig, *, indent=4
) -> str:
    """Creates the default info.json for a new FPP question, with a unique v4 UUID.
    Expects `question_name` to be lower snake case.
    """
    question_title = " ".join(map(str.capitalize, question_name.split("_")))

    info_json = {
        "uuid": str(uuid4()),
        "title": question_title,
        "topic": "",
        "tags": ["berkeley", "fp"],
        "type": "v3",
    }

    info_json.update(autograder.info_json_update())

    return dumps(info_json, indent=indent) + "\n"


def generate_fpp_question(source_path: Path, *, options: Options):
    """Takes a path of a well-formatted source (see `extract_prompt_ans`),
    then generates and populates a question directory of the same name.
    """

    if options.verbosity > -1:
        consts.Bcolors.info("Generating from source", source_path)

    if options.verbosity > 0:
        print("- Extracting from source...")

    source_path = io_helpers.resolve_path(source_path)
    source_code = source_path.read_text()
    tokens = lex(source_code, source_path=source_path)
    regions = parse_fpp_regions(tokens)

    def remove_region(key: str, default="") -> str:
        return regions.pop(key, default) #type: ignore

    metadata = regions["metadata"]
    metadata.setdefault("autograder", source_path.suffix)
    options = options.with_metadata(metadata)

    autograder: AutograderConfig = new_autograder_from_ext(options.ag_extension)

    q_dir = options.out_path if options.out_path is not None else source_path.parent

    question_name = source_path.stem
    if options.make_dir:
        # create all new content in a new folder that is a
        # sibling of the source file in the filesystem
        question_dir = q_dir / question_name
    else:
        question_dir = q_dir
    test_dir = question_dir / "tests"

    if options.verbosity > 0:
        print("- Creating destination directories...")

    io_helpers.make_if_absent(question_dir)
    io_helpers.make_if_absent(test_dir)

    copy_dest_path = question_dir / "source.py"
    if options.verbosity > 0:
        print(f"- Copying {source_path.name} to {copy_dest_path} ...")
    copyfile(source_path, copy_dest_path)

    setup_code = remove_region("setup_code", consts.SETUP_CODE_DEFAULT)
    answer_code = remove_region("answer_code")
    server_code = remove_region("server")
    prompt_code = remove_region("prompt_code")
    question_text = remove_region("question_text")

    if options.verbosity > 0:
        print("- Populating {} ...".format(question_dir))

    gen_server_code, setup_names, _answer_names = autograder.generate_server(
        setup_code=setup_code, answer_code=answer_code, no_ast=(not options.do_parse)
    )
    server_code = server_code or gen_server_code

    question_html = generate_question_html(
        prompt_code,
        question_text=question_text,
        setup_names=setup_names,
        element_attrs=_question_element_attrs_from_metadata(metadata),
    )

    io_helpers.write_to(question_dir, "question.html", question_html)
    io_helpers.write_to(question_dir, "server.py", server_code)
    io_helpers.write_to(question_dir, "solution", answer_code)

    json_path = question_dir / "info.json"
    json_region = remove_region("info.json")
    missing_json = not json_path.exists()
    if options.force_generate_json or json_region or missing_json:
        json_text = json_region or generate_info_json(question_name, autograder)
        io_helpers.write_to(question_dir, "info.json", json_text)
        if not missing_json:
            consts.Bcolors.warn(
                "  - Overwriting",
                json_path,
                'using "info.json" region...' if json_region else "...",
            )

    if options.verbosity > 0:
        print("- Populating {} ...".format(test_dir))

    test_region = remove_region("test")

    autograder.populate_tests_dir(
        test_dir,
        answer_code,
        setup_code,
        test_region,
        log_details=options.verbosity > 0,
    )

    if metadata:
        io_helpers.write_to(question_dir, "metadata.json", options.dump())

    if regions:
        consts.Bcolors.warn("- Writing unrecognized regions:")

    for raw_path in regions:
        if raw_path == "metadata":
            continue

        if not raw_path:
            consts.Bcolors.warn("  - Skipping anonymous region!")
            continue

        # if no file extension is given, give it .py (removed due to Gemfile)
        # if not file_ext(raw_path):
        #     raw_path += '.py'

        # ensure that the directories exist before writing
        final_path = question_dir / Path(raw_path)
        io_helpers.make_if_absent(final_path.parent)
        consts.Bcolors.warn("  -", final_path, "...")

        # write files
        io_helpers.write_to(question_dir, raw_path, regions[raw_path])

    autograder.clean_tests_dir(test_dir)

    consts.Bcolors.printf(consts.Bcolors.OK_GREEN, "Done.")


def generate_many(args: Namespace):
    if not args.source_paths:
        args.source_paths = io_helpers.auto_detect_sources()

    def generate_one(source_path, force_json=False):
        options = Options.build(args, force_json=force_json)

        try:
            generate_fpp_question(source_path, options=options)
            return True
        except SyntaxError as e:
            consts.Bcolors.fail("SyntaxError:", e.msg)
        except OSError as e:
            consts.Bcolors.fail("FileNotFoundError:", *e.args)

        return False

    successes, failures = 0, 0

    for source_path in args.source_paths:
        if generate_one(source_path):
            successes += 1
        else:
            failures += 1

    for source_path in args.force_json:
        if generate_one(source_path, force_json=True):
            successes += 1
        else:
            failures += 1

    # print batch feedback
    if successes + failures > 1:

        def n_files(n):
            return str(n) + " file" + ("" if n == 1 else "s")

        if successes:
            consts.Bcolors.ok(
                "Batch completed successfully on", n_files(successes), end=""
            )
            if failures:
                consts.Bcolors.fail(" and failed on", n_files(failures))
            else:
                print()
        else:
            consts.Bcolors.fail("Batch failed on all", n_files(failures))


def profile_generate_many(args: Namespace):
    from cProfile import Profile
    from pstats import Stats, SortKey

    with Profile() as pr:
        generate_many(args)

    stats = Stats(pr)
    stats.sort_stats(SortKey.TIME)
    print("\n---------------\n")
    stats.print_stats()


def main():
    args = io_helpers.parse_args()

    if args.profile:
        profile_generate_many(args)
    else:
        generate_many(args)


if __name__ == "__main__":
    main()
