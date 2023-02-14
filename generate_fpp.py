from collections import defaultdict
from enum import IntEnum
from json import dumps
from os import path, PathLike
from re import match as test
from shutil import copyfile
from uuid import uuid4

from lib.consts import *
from lib.io_helpers import *

from lib.tokens import Tokens, Token, TokenType, lex, regex_chunk_lines
from lib.name_visitor import AnnotatedName
from lib.autograde import AutograderConfig, autograders, PythonAutograder

def parse_blanks(source_path: str, tkn: Token, blank_re: Pattern):
    itr = regex_chunk_lines(blank_re, tkn.text, line_number=tkn.lineno)
    # (exclusive) end of the last match
    for line_number, found, chunk in itr:
        if found:
            # non-None
            blank, = chunk.groups()
            if not blank:
                # only possible with custom regexes.
                raise SyntaxError(
                    'blankDelimiter Regex captured empty text at '
                        + format_ln(source_path, line_number))

            yield (blank, BLANK_SUBSTITUTE)
        else:
            yield (chunk, chunk)


def parse_fpp_regions(tokens: Tokens):
    if 'blankDelimiter' in tokens.metadata:
        blank_re = make_blank_re(tokens.metadata['blankDelimiter'])
    else:
        blank_re = DEFAULT_BLANK_PATTERN

    r_texts: dict[str, list[str]] = defaultdict(list)
    answer, prompt = r_texts['answer_code'], r_texts['prompt_code']

    class DocstringState(IntEnum):
        Accepting = 0
        FollowWithNewline = 1
        Finished = 2
        Skipped = 3

    docstring_state = DocstringState.Accepting
    for tkn in tokens.data:
        if not tkn.text: continue

        if tkn.region:
            if tkn.region == 'question_text' and docstring_state == DocstringState.FollowWithNewline:
                r_texts[tkn.region].append('\n')
                docstring_state = DocstringState.Finished
            r_texts[tkn.region].append(tkn.text)
            continue

        if tkn.type == TokenType.DOCSTRING:
            if docstring_state == DocstringState.Accepting:
                qs = r_texts['question_text']
                if qs:
                    qs.append('\n')
                    docstring_state = DocstringState.Finished
                else:
                    docstring_state = DocstringState.FollowWithNewline
                qs.append(tkn.text[3:-3])
            else:
                prompt.append(tkn.text)
                answer.append(tkn.text)
        elif tkn.type == TokenType.COMMENT:
            target = prompt if test(SPECIAL_COMMENT_PATTERN, tkn.text) \
                else answer
            target.append(tkn.text)
        elif tkn.type == TokenType.STRING:
            prompt.append(tkn.text)
            answer.append(tkn.text)
        elif tkn.type == TokenType.UNMATCHED:
            for ans, prmpt in parse_blanks(tokens.source_path, tkn, blank_re):
                answer.append(ans)
                prompt.append(prmpt)
        else:
            raise Exception("Unreachable! Inexhaustive token types: " + str(tkn.type))

        docstring_state = docstring_state or DocstringState.Skipped

    out = { 'metadata': tokens.metadata }
    for k, region_list in r_texts.items():
        ls = ''.join(region_list)
        ls = map(str.rstrip, ls.splitlines())
        if k == 'prompt_code':
            ls = filter(bool, ls)
        out[k] = '\n'.join(ls).strip()

    return out


def generate_question_html(
    prompt_code: str, *,
    question_text: str = None,
    tab: str = '  ',
    setup_names: list[AnnotatedName] = None,
    answer_names: list[AnnotatedName] = None
) -> str:
    """Turn an extracted prompt string into a question html file body"""
    indented = prompt_code.replace('\n', '\n' + tab)

    if question_text is None:
        question_text = tab + '<!-- Write the question prompt here -->'
    elif setup_names or answer_names:
        question_text = tab + '<h3> Prompt </h3>\n' + tab + question_text

        question_text += '\n\n<markdown>\n'

        def format_annotated_name(name: AnnotatedName) -> str:
            out = ' - `' + name.id
            if name.annotation:
                out += ': ' + name.annotation
            out += '`'
            if name.description:
                out += ', ' + name.description
            return out

        if setup_names:
            question_text += '### Provided\n'
            question_text += '\n'.join(map(format_annotated_name, setup_names))
            if answer_names:
                question_text += '\n\n'

        if answer_names:
            question_text += '### Required\n'
            question_text += '\n'.join(
                map(format_annotated_name, answer_names))

        question_text += '\n</markdown>\n'

    return """<!-- AUTO-GENERATED FILE -->
<pl-question-panel>
{question_text}
</pl-question-panel>

<!-- see README for where the various parts of question live -->
<pl-faded-parsons>
{tab}{indented}
</pl-faded-parsons>""".format(question_text=question_text, tab=tab, indented=indented)


def generate_info_json(question_name: str, autograder: AutograderConfig, *, indent=4) -> str:
    """ Creates the default info.json for a new FPP question, with a unique v4 UUID.
        Expects `question_name` to be lower snake case.
    """
    question_title = ' '.join(l.capitalize() for l in question_name.split('_'))

    info_json = {
        'uuid': str(uuid4()),
        'title': question_title,
        'topic': '',
        'tags': ['berkeley', 'fp'],
        'type': 'v3',
    }

    info_json.update(autograder.info_json_update())

    return dumps(info_json, indent=indent) + '\n'


def generate_fpp_question(
    source_path: PathLike[AnyStr], *,
    force_generate_json: bool = False,
    no_parse: bool = False,
    log_details: bool = True,
):
    """ Takes a path of a well-formatted source (see `extract_prompt_ans`),
        then generates and populates a question directory of the same name.
    """
    Bcolors.info('Generating from source', source_path)

    source_path = resolve_path(source_path)

    extension = file_ext(source_path)
    ag = autograders.get(extension, PythonAutograder)
    autograder: AutograderConfig = ag()

    if log_details:
        print('- Extracting from source...')

    with open(source_path, 'r') as source:
        source_code = ''.join(source)
        tokens = lex(source_code, source_path=source_path)
        regions = parse_fpp_regions(tokens)

    def remove_region(key, default=''):
        if key in regions:
            v = regions[key]
            del regions[key]
            return v
        return default

    metadata = remove_region('metadata')

    force_generate_json = metadata.get('forceGenerateJson', force_generate_json)
    no_parse = metadata.get('noParse', no_parse)

    question_name = file_name(source_path)

    # create all new content in a new folder that is a
    # sibling of the source file in the filesystem
    question_dir = path.join(path.dirname(source_path), question_name)

    if log_details:
        print('- Creating destination directories...')

    test_dir = path.join(question_dir, 'tests')
    make_if_absent(test_dir)

    copy_dest_path = path.join(question_dir, 'source.py')
    if log_details:
        print('- Copying {} to {} ...'.format(path.basename(source_path), copy_dest_path))
    copyfile(source_path, copy_dest_path)

    if log_details:
        print('- Populating {} ...'.format(question_dir))

    setup_code = remove_region('setup_code', SETUP_CODE_DEFAULT)
    answer_code = remove_region('answer_code')

    server_code = remove_region('server')
    gen_server_code, setup_names, answer_names = autograder.generate_server(
        setup_code=setup_code,
        answer_code=answer_code,
        no_ast=no_parse
    )
    server_code = server_code or gen_server_code

    prompt_code = remove_region('prompt_code')
    question_text = remove_region('question_text')

    question_html = generate_question_html(
        prompt_code,
        question_text=question_text,
        setup_names=setup_names,
        # show_required removed:
        # answer_names=answer_names if show_required else None
    )

    write_to(question_dir, 'question.html', question_html)

    write_to(question_dir, 'solution', answer_code)

    json_path = path.join(question_dir, 'info.json')
    json_region = remove_region('info.json')
    missing_json = not path.exists(json_path)
    if force_generate_json or json_region or missing_json:
        json_text = json_region or generate_info_json(question_name, autograder)
        write_to(question_dir, 'info.json', json_text)
        if not missing_json:
            Bcolors.warn('  - Overwriting', json_path,
                         'using \"info.json\" region...' if json_region else '...')

    write_to(question_dir, 'server.py', server_code)

    if log_details:
        print('- Populating {} ...'.format(test_dir))

    test_region = remove_region('test')

    autograder.populate_tests_dir(
        test_dir,
        answer_code,
        setup_code,
        test_region,
        log_details = log_details
    )

    if metadata:
        write_to(question_dir, 'metadata.json', dumps(metadata))

    if regions:
        Bcolors.warn('- Writing unrecognized regions:')

    for raw_path, data in regions.items():
        if not raw_path:
            Bcolors.warn('  - Skipping anonymous region!')
            continue

        # if no file extension is given, give it .py
        if not file_ext(raw_path):
            raw_path += '.py'

        # ensure that the directories exist before writing
        final_path = path.join(question_dir, raw_path)
        make_if_absent(path.dirname(final_path))
        Bcolors.warn('  -', final_path, '...')

        # write files
        write_to(question_dir, raw_path, data)

    Bcolors.printf(Bcolors.OK_GREEN, 'Done.')


def generate_many(args: Namespace):
    if not args.source_paths:
        args.source_paths = auto_detect_sources()

    def generate_one(source_path, force_json=False):
        try:
            generate_fpp_question(
                source_path,
                force_generate_json=force_json,
                no_parse=args.no_parse,
                log_details=not args.quiet
            )
            return True
        except SyntaxError as e:
            Bcolors.fail('SyntaxError:', e.msg)
        except OSError as e:
            Bcolors.fail('FileNotFoundError:', *e.args)

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
        def n_files(n): return str(n) + ' file' + ('' if n == 1 else 's')
        if successes:
            Bcolors.ok('Batch completed successfully on', n_files(successes), end='')
            if failures:
                Bcolors.fail(' and failed on', n_files(failures))
            else:
                print()
        else:
            Bcolors.fail('Batch failed on all', n_files(failures))


def profile_generate_many(args: Namespace):
    from cProfile import Profile
    from pstats import Stats, SortKey

    with Profile() as pr:
        generate_many(args)

    stats = Stats(pr)
    stats.sort_stats(SortKey.TIME)
    print('\n---------------\n')
    stats.print_stats()


def main():
    args = parse_args()

    if args.profile:
        profile_generate_many(args)
    else:
        generate_many(args)


if __name__ == '__main__':
    main()
