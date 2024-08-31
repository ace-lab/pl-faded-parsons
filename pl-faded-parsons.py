try:
    import prairielearn as pl
except ModuleNotFoundError:
    print('<!> pl not loaded! <!>')

from typing import Union, List, Dict
from datetime import datetime

import base64
import chevron
import itertools
import json
import os.path
import random
import re
import lxml.html as xml


from abc import ABC, abstractmethod
from dataclasses import asdict, dataclass


#
# Common Interfaces for Parsing External Data
#
Jsonish = Union[bool, float, int, str, List['Jsonish'], Dict[str, 'Jsonish']] # TODO: make sure this is possible in 3.8

@dataclass
class Submission:

    @dataclass
    class Line:
        indent: int
        codeSnippets: list[str]
        blankValues: list[str]

    @dataclass
    class Trays:
        solution: List["Submission.Line"]
        starter: Union[List["Submission.Line"], None] = None

    @dataclass
    class LogEntry:
        timestamp: datetime
        tag: str # this is technically an enum of string literals ... Maybe enumerate eventually?
        data: dict # TODO: expand this, the "tag" tells us the type of JSON object this is

    main: Trays
    log: List[LogEntry] = field(default_factory=list)

@dataclass
class Mustache:

    @dataclass
    class Line:

        @dataclass
        class CodeSegment:
            @dataclass
            class InnerData:
                content: str
                language: str
            
            code: InnerData
            # { 'code': { 'content': value, 'language': language } }

        @dataclass
        class BlankSegment:
            @dataclass
            class InnerData:
                default: str
                width: str # max(4, len(value) + 1)
            
            blank: InnerData

        indent: int
        segments: List[Union[CodeSegment, BlankSegment]]

    @dataclass
    class TrayLines:
        lines: List[Mustache.Line] # [Line.to_mustache(l, lang) for l in lines]
        size: bool = True # any truthy value will do

    # chevron skips rendering when values are falsy (eg pre-text/post-text/starter)

    # main element config
    answers_name : str
    language : str
    previous_log : str # json.dumps(prev_submission.log)
    uuid: pl.get_uuid()

    # trays and code context
    "starter": use_starter_tray and tray_lines_to_mustache(state.starter),
    pre_text: str
    "given": tray_lines_to_mustache(state.solution),
    post_text: str

class FadedParsonsProblem:

    class Formats:
        BOTTOM = "bottom"
        RIGHT = "right"
        NO_CODE = "no_code"

    def __init__(self, element_html):

        def get_child_text_by_tag(element, tag: str) -> str:
            """get the innerHTML of the first child of `element` that has the tag `tag`
            default value is empty string"""
            return next((elem.text for elem in element if elem.tag == tag), "")

        element = xml.fragment_fromstring(element_html)

        self.answers_name = pl.get_string_attrib(element, 'answers-name', '')
        if self.answers_name == "":
            raise ValueError() # FIXME: fill error message

        self.format = FadedParsonsProblem.Formats(
            pl.get_string_attrib(element, "format", "right")
                .replace("-", '_')
        )

        self.pre_text  = get_child_text_by_tag(element, "pre-text").strip("\n")
        self.post_text = get_child_text_by_tag(element, "post-text").strip("\n")

        self.language = pl.get_string_attrib(element, "language", None)

        self.size = "narrow" if self.format == FadedParsonsProblem.Formats.RIGHT else "wide"

        if self.format == FadedParsonsProblem.Formats.RIGHT and pre_text or post_text:
            raise Exception("pre-text and post-text are not supported in right (horizontal) mode. " +
                'Add/set `format="bottom"` or `format="no-code"` to your element to use this feature.')


        if not (markup := get_child_text_by_tag(element, "code-lines")):
            try:
                path = os.path.join(data["options"]["question_path"], 'serverFilesQuestion', 'code_lines.txt') # TODO: fix dict accessing
                with open(path, 'r') as f:
                    markup = f.read()
            except:
                markup = str(element.text)

        ############ here

        parsed_lines = map(Line.from_fpp_str, markup.strip().split('\n'))

        starters, givens, distractors = [], [], []
        for kind, line in parsed_lines:
            if kind == 'given':
                givens.append(line)
            elif kind == 'distractor':
                distractors.append(line)
            elif kind == 'starter':
                starters.append(line)
            else:
                raise ValueError(f'unrecognized line kind: {kind}')

        distractor_count = min(len(distractors), max_distractors)
        starters.extend(random.sample(distractors, k=distractor_count))

        state = ProblemState(starters, givens)

        random.shuffle(state.starter)

        if format == 'no_code':
            state = ProblemState([], state.solution + state.starter)

        tray_lines_to_mustache = lambda lines: {
            "lines": [Line.to_mustache(l, lang) for l in lines],
            size: True # any truthy value will do
        }

        html_params = asdict(Mustache(...))

        with open('pl-faded-parsons-question.mustache', 'r') as f:
            return chevron.render(f, html_params).strip()

@dataclass
class ProblemState:
    
    @dataclass
    class Metadata:
        answers_name: str
        ...
    
    @dataclass
    class Line:
        ...

        @dataclass
        class Schema:
            # using Line(**line) breaks when any extra info is passed in, which is desirable to enforce the schema
            indent: int
            codeSnippets: list[str]
            blankValues: list[str]

            def __post_init__(self):
                if len(self.codeSnippets) != len(self.blankValues) + 1:
                    raise ValueError('codeSnippets must have one more element than blankValues')

        @staticmethod
        def from_markup(markup: str) -> Tuple[str, "Line"]:
            BLANK = re.compile(r'#blank [^#]*')
            GIVEN = re.compile(r'#(\d+)given')
            DISTRACTOR = re.compile(r'#distractor')

            snippets = markup.strip().split('!BLANK')

            def remove_special_comment(parser, pattern):
                nonlocal snippets
                if match := parser(pattern, snippets[-1]):
                    snippets[-1] = re.sub(pattern, '', snippets[-1]).rstrip()
                return match

            blanks = [''] * (len(snippets) - 1)
            if blank_defaults := remove_special_comment(re.findall, BLANK):
                for i, val in enumerate(blank_defaults):
                    blanks[i] = val.replace('#blank', '').strip()

            if match := remove_special_comment(re.search, GIVEN):
                return 'given', Line(int(match.group(1)), snippets, blanks)

            if remove_special_comment(re.search, DISTRACTOR):
                return 'distractor', Line(0, snippets, blanks)

            return 'starter', Line(0, snippets, blanks)

        @staticmethod
        def from_submission(raw_submission_data: dict) -> "Line":
            # raw sub data should already be indexed into the answers_name and this should be a Line
            s = recursive_instantiate(Submission.Line.Schema, raw_submission_data)

        
        def to_display_code(self):
            ...

    metadata: Metadata
    starter_lines: Union[List[Line], None] = None
    s_lines: Union[List[Line], None] = None


    @staticmethod
    def from_xml(element_html) -> "ProblemState":
        ...

    def load_submission_data(self, data: dict) -> "ProblemState":
        ...

    def to_mustache(self) -> dict[str, Jsonish]:
        ...


class FromPrairieLearn(ABC):
    '''
    an interface for serializing data transmitted through the input elements in
    pl-faded-parsons-question.mustache, by way of pl's data dict
    '''
    @staticmethod
    @abstractmethod
    def from_pl_data(data: dict[str, Jsonish], *args):
        '''
        import this record from prairielearn submission storage (either
        `data["raw_submitted_answers"]` or `data["submitted_answers"]`)
        '''
        pass

    def to_pl_data(self) -> dict[str, Jsonish]:
        'export this for pl-faded-parsons-question.mustache input storage'
        return asdict(self)

    @staticmethod
    def make_key(answers_name: str, input_name: str): return f'{answers_name}.{input_name}'

    @staticmethod
    def read_pl_data(answers_data: dict, answers_name: str, input_name: str, default: Jsonish) -> Jsonish:
        """
        Retrieve the value of `input_name` under `answers_name` in `answers_data`.
        If not found, return `default`.
        If found, parse the retrieved value to match the type of `default`, raising an error on failure.
        """
        key = FromPrairieLearn.make_key(answers_name, input_name)
        if key not in answers_data: return default

        value = answers_data[key]
        default_type = type(default)

        # if we aren't expecting a str out, then attempt parsing
        if type(value) is str and default_type is not str:
            if not value: return default
            value = json.loads(value)

        if type(value) is default_type: return value

        raise TypeError(f'expected input.{input_name} to store a {default_type} but got:\n{repr(value)}')


class FromUser(ABC):
    '''
    an interface for reading in data from a use of the pl-faded-parsons
    element by a question content author (usually an instructor)
    '''
    @staticmethod
    @abstractmethod
    def from_fpp_str(raw: str):
        'parse raw low-level fpp markup'
        pass

    @abstractmethod
    def to_code_str(self) -> str:
        'flatten this representation into raw student code'
        pass


#
# Helpful Record Types
#
@dataclass(frozen=True, slots=True)
class Line(FromPrairieLearn, FromUser):
    '''
    A helper class for reading, storing, and writing common line data.

    Import/export uses the schema in pl-faded-parsons.js `storeStudentProgress`.
    Expects a line to have the type:
    ``` ts
    type Codeline = {
        indent: number,
        codeSnippets: string[],
        blankValues: string[],
    };
    ```
    where `codeSnippets.length() == 1 + blankValues.length()`
    '''
    indent: int
    codeSnippets: list[str]
    blankValues: list[str]

    def __post_init__(self):
        if len(self.codeSnippets) != len(self.blankValues) + 1:
            raise ValueError('codeSnippets must have one more element than blankValues')

    def from_pl_data(line: dict) -> 'Line':
        # using Line(**line) breaks when any extra info is passed in 
        return Line(line['indent'], line['codeSnippets'], line['blankValues'])

    def from_fpp_str(raw_line: str):
        BLANK = re.compile(r'#blank [^#]*')
        GIVEN = re.compile(r'#(\d+)given')
        DISTRACTOR = re.compile(r'#distractor')

        snippets = raw_line.strip().split('!BLANK')

        def remove_special_comment(parser, pattern):
            nonlocal snippets
            if match := parser(pattern, snippets[-1]):
                snippets[-1] = re.sub(pattern, '', snippets[-1]).rstrip()
            return match

        blanks = [''] * (len(snippets) - 1)
        if blank_defaults := remove_special_comment(re.findall, BLANK):
            for i, val in enumerate(blank_defaults):
                blanks[i] = val.replace('#blank', '').strip()

        if match := remove_special_comment(re.search, GIVEN):
            return 'given', Line(int(match.group(1)), snippets, blanks)

        if remove_special_comment(re.search, DISTRACTOR):
            return 'distractor', Line(0, snippets, blanks)

        return 'starter', Line(0, snippets, blanks)

    def to_code_str(self) -> str:
        indent = self.indent * ' '
        return indent + ''.join(s for _, s in self)

    def to_mustache(self, language, *, indent_size=4) -> dict[str, Jsonish]:
        'matches schemas in pl-faded-parsons-code-line.mustache'
        return {
            "indent": self.indent * indent_size,
            "segments": [
                { 'code': { 'content': value, 'language': language } } \
                    if is_code else \
                { 'blank': { 'default': value, 'width': max(4, len(value) + 1) } }
                    for is_code, value in self
            ],
        }

    def __iter__(self):
        for x, y in zip(self.codeSnippets, self.blankValues):
            yield True,  x
            yield False, y
        yield True, self.codeSnippets[-1]


@dataclass(frozen=True, slots=True)
class ProblemState(FromPrairieLearn, FromUser):
    '''
    Loads the contents of input.main in pl-faded-parsons-question.mustache
    according to the schema in pl-faded-parsons.js `storeStudentProgress`,
    or parses the low-level faded parsons markdown generated by FPPgen or
    an end user.
    '''
    starter: list[Line]
    solution: list[Line]

    def from_pl_data(answers_data: dict, answers_name: str) -> 'ProblemState':
        'works for `data["raw_submitted_answers"]` and `data["submitted_answers"]`'

        def import_lines(mem: dict, entry: str):
            return [Line.from_pl_data(l) for l in mem.get(entry, [])]

        main_memory = FromPrairieLearn.read_pl_data(answers_data, answers_name, 'main', {})

        return ProblemState(
            import_lines(main_memory, 'starter'),
            import_lines(main_memory, 'solution'),
        )

    def from_fpp_str(raw_text: str, *, max_distractors=10) -> 'ProblemState':
        parsed_lines = map(Line.from_fpp_str, raw_text.strip().split('\n'))

        starters, givens, distractors = [], [], []
        for kind, line in parsed_lines:
            if kind == 'given':
                givens.append(line)
            elif kind == 'distractor':
                distractors.append(line)
            elif kind == 'starter':
                starters.append(line)
            else:
                raise ValueError(f'unrecognized line kind: {kind}')

        distractor_count = min(len(distractors), max_distractors)
        starters.extend(random.sample(distractors, k=distractor_count))

        return ProblemState(starters, givens)

    def to_code_str(self):
        return '\n'.join(map(Line.to_code_str, self.solution))

    def __bool__(self): return bool(self.starter or self.solution)


@dataclass(frozen=True, slots=True)
class Submission(FromPrairieLearn):
    '''
    Record that loads submission data from the PL `data` param. Save locations
    set by the `input` elements in pl-faded-parsons-question.mustache.
    `answers_name` is the problem name passed in the `element_html`.
    '''
    answers_name: str
    problem_state: ProblemState
    log: list[dict]

    def from_pl_data(answers_name: str, answers_data: dict):
        return Submission(
            answers_name,
            ProblemState.from_pl_data(answers_data, answers_name),
            FromPrairieLearn.read_pl_data(answers_data, answers_name, 'log', []),
        )

    def to_pl_data(self) -> dict[str, str]:
        def entry(k, v): return FromPrairieLearn.make_key(self.answers_name, k), json.dumps(v)
        return dict((
            entry('main', self.problem_state.to_pl_data()),
            entry('log', self.log),
        ))


#
# Helper functions
#
def get_answers_name(element):
    'answers-name namespaces answers for multiple elements on a page'
    return pl.get_string_attrib(element, 'answers-name', '')


def render_question_panel(element_html, data):
    """Render the panel that displays the question (from code_lines.txt) and interaction boxes"""
    def get_child_text_by_tag(element, tag: str) -> str:
        """get the innerHTML of the first child of `element` that has the tag `tag`
        default value is empty string"""
        return next((elem.text for elem in element if elem.tag == tag), "")

    def code_context_to_mustache(element, tag, lang):
        if text := get_child_text_by_tag(element, tag).strip("\n"):
            return { "text": text, "language": lang }
        return None

    def load_new_state(element, use_starter_tray) -> ProblemState:
        raw_lines = get_child_text_by_tag(element, "code-lines")

        if not raw_lines:
            try:
                path = os.path.join(data["options"]["question_path"], 'serverFilesQuestion', 'code_lines.txt')
                with open(path, 'r') as f:
                    raw_lines = f.read()
            except:
                raw_lines = str(element.text)

        state: ProblemState = ProblemState.from_fpp_str(raw_lines)

        random.shuffle(state.starter)

        if use_starter_tray:
            return state

        return ProblemState([], state.solution + state.starter)

    def get_format_and_size(element, has_pre_or_post_text):
        format = pl.get_string_attrib(element, "format", "right").replace("-", '_')
        if format not in ("bottom", "right", "no_code"):
            raise Exception(f"Unsupported pl-faded-parsons format: {repr(format)}. Please see documentation for supported formats")

        size = "wide"

        if format == "right":
            if has_pre_or_post_text:
                raise Exception("pre-text and post-text are not supported in right (horizontal) mode. " +
                    'Add/set `format="bottom"` or `format="no-code"` to your element to use this feature.')
            size = "narrow"

        return format, size


    element = xml.fragment_fromstring(element_html)

    answers_name = get_answers_name(element)
    lang = pl.get_string_attrib(element, "language", None)

    pre_text  = code_context_to_mustache(element, "pre-text",  lang)
    post_text = code_context_to_mustache(element, "post-text", lang)

    format, size = get_format_and_size(element, pre_text or post_text)
    use_starter_tray = format != 'no_code'

    prev_submission: Submission = Submission.from_pl_data(answers_name, data['submitted_answers'])
    state = prev_submission.problem_state or load_new_state(element, use_starter_tray)

    tray_lines_to_mustache = lambda lines: {
        "lines": [Line.to_mustache(l, lang) for l in lines],
        size: True # any truthy value will do
    }

    # chevron skips rendering when values are falsy (eg pre-text/post-text/starter)
    html_params = {
        # main element config
        "answers-name": answers_name,
        "language": lang,
        "previous-log" : json.dumps(prev_submission.log),
        "uuid": pl.get_uuid(),

        # trays and code context
        "starter": use_starter_tray and tray_lines_to_mustache(state.starter),
        "pre-text": pre_text,
        "given": tray_lines_to_mustache(state.solution),
        "post-text": post_text,
    }

    with open('pl-faded-parsons-question.mustache', 'r') as f:
        return chevron.render(f, html_params).strip()


def render_submission_panel(element_html, data):
    """Show student what they submitted"""
    element = xml.fragment_fromstring(element_html)
    answers_name = get_answers_name(element)
    problem_state: ProblemState = ProblemState.from_pl_data(data['submitted_answers'], answers_name)
    html_params = {
        'code': problem_state.to_code_str(),
    }
    with open('pl-faded-parsons-submission.mustache', 'r') as f:
        return chevron.render(f, html_params).strip()


def render_answer_panel(element_html, data):
    """Show the instructor's reference solution"""
    element = xml.fragment_fromstring(element_html)
    path = pl.get_string_attrib(element, 'solution-path', './solution')

    if not os.path.exists(path):
        raise FileNotFoundError(f'\n\tCorrect answer not found at `{path}`! \n\tProvide an answer or set "showCorrectAnswer" to false in `./info.json`')

    html_params = {
        "solution_path": path,
    }
    with open('pl-faded-parsons-answer.mustache', 'r') as f:
        return chevron.render(f, html_params).strip()


#
# Main functions
#
def render(element_html, data):
    panel_type = data['panel']
    if panel_type == 'question':
        return render_question_panel(element_html, data)
    elif panel_type == 'submission':
        return render_submission_panel(element_html, data)
    elif panel_type == 'answer':
        return render_answer_panel(element_html, data)
    else:
        raise Exception(f'Invalid panel type: {panel_type}')


def parse(element_html, data):
    """Parse student's submitted answer (HTML form submission)"""
    def base64_encode(s):
        return base64.b64encode(s.encode("ascii")).decode("ascii")

    element = xml.fragment_fromstring(element_html)
    answers_name = get_answers_name(element)
    file_name = pl.get_string_attrib(element, 'file-name', 'user_code.py')

    submission: Submission = Submission.from_pl_data(answers_name, data['raw_submitted_answers'])
    student_code = submission.problem_state.to_code_str()

    data['submitted_answers'].update(submission.to_pl_data())
    data['submitted_answers'].update({
        '_files': [
            {
                "name": file_name,
                "contents": base64_encode(student_code)
            }
        ],
        # provide the answer to users of pl-faded-parsons in classic PL style
        answers_name: student_code,
    })
