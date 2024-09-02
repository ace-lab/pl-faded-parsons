try:
    import prairielearn as pl
except ModuleNotFoundError:
    print('<!> pl not loaded! <!>')

import base64
import chevron
import json
import os.path
import random
import re
import lxml.html as xml

from dataclasses import asdict, dataclass, field, is_dataclass
from typing import Union, List, Dict, Literal, Any, get_args, get_origin, cast
from datetime import datetime
from enum import Enum

UnionType = Union # replace with an import when python>=3.10
NoneType = type(None) # replace with an import when python>=3.10

#
# Common Interfaces for Parsing/Generating Data
#

@dataclass(frozen=True)
class Submission:
    '''
    Represent the contents of input.main and input.log from pl-faded-parsons-question.mustache
    '''

    @dataclass(frozen=True)
    class Line:
        indent: int
        codeSnippets: List[str]
        blankValues: List[str]

        def __post_init__(self):
            if len(self.codeSnippets) != len(self.blankValues) + 1:
                raise ValueError('codeSnippets must have one more element than blankValues')

    @dataclass(frozen=True)
    class Trays:
        solution: List["Submission.Line"]
        starter: Union[List["Submission.Line"], None] = None

    @dataclass(frozen=True)
    class LogEntry:
        timestamp: datetime
        tag: str # this is technically an enum of string literals ... Maybe enumerate eventually?
        data: dict # TODO: expand this, the "tag" tells us the type of JSON object this is

    main: Trays
    log: List[LogEntry] = field(default_factory=list)

@dataclass(frozen=True)
class Mustache:

    @dataclass(frozen=True)
    class Line:

        @dataclass(frozen=True)
        class Segment:
            @dataclass
            class Blank:
                default: str
                width: int

            @dataclass
            class Code:
                content: str
                language: str

            # { 'blank': { 'default': ..., 'width': max(4, len(...) + 1) } }
            blank: Union[Blank, None] = None
            # { 'code': { 'content': ..., 'language': ... } }
            code: Union[Code, None] = None

        indent: int
        segments: List[Segment]

    @dataclass(frozen=True)
    class TrayLines:
        lines: List["Mustache.Line"] # [Line.to_mustache(l, lang) for l in lines]
        size: bool = True # any truthy value will do

    # chevron skips rendering when values are falsy (eg pre-text/post-text/starter)

    # main element config
    answers_name : str
    language : str
    previous_log : str
    uuid: str

    # trays and code context
    starter: Union[TrayLines, Literal['']]
    pre_text: str
    given: TrayLines
    post_text: str

#
# Helper Routines
#

def get_child_text_by_tag(element, tag: str) -> str:
    """get the innerHTML of the first child of `element` that has the tag `tag`
    default value is empty string"""
    return next((elem.text for elem in element if elem.tag == tag), "")

class ParsingError(Exception):
    '''Something went wrong during parsing'''

def validate_and_instantiate(t: type, value: Any): # add generic typing when python>=3.12 (i.e. `val_and_inst[T](t: T, value: Any) -> T`)
    """
    Validate that `value` (a primitive type) can be converted to `t`.
    If so, returns an instance of `t`. Raises a ParsingError otherwise.
    """

    if isinstance(t, UnionType):
        annotated_types = get_args(t)

        if NoneType in annotated_types and value is None: # fast return for common case
            return None

        casts = [ ]
        for t in annotated_types: # for each type that isn't None:
            if issubclass(t, NoneType): continue

            try: # try to cast it to each anotation, skipping ones that error
                singly_typed = validate_and_instantiate(t, value)
                if singly_typed is None:
                    continue

                casts.append((singly_typed, t))
            except TypeError as _:
                pass

        if casts == [ ]:
            raise ParsingError(f"None of {annotated_types} can be constructed from: {value}")
        elif len(casts) > 1: # multiple casts worked -- that's bad
            matching_types = list(map(lambda x: x[1], casts))
            raise ParsingError(f"Ambiguous type! All of {matching_types} could be constructed from: {value}")

        return casts[0][0]

    if is_dataclass(t):
        return t(**{
            k: validate_and_instantiate(t.__annotations__[k], v)
            for k, v in value.items()
        })

    # this is the `List` in `List[int]`, is None if just `list`
    wanted_type = get_origin(t) 
    if wanted_type == None:
        # `t` is a class that's not a dataclass with no annotations, cast it
        return t(value)
    
    # this is the `(int,)` in `List[int]`, is `tuple()` if just `list`/`List`
    type_args = get_args(t)
    if len(type_args) == 0:
        return wanted_type(value)

    if wanted_type == list and isinstance(value, list): 
        # `List`/`list` only accepts one type argument
        item_type = type_args[0]
        return list(
            validate_and_instantiate(item_type, v)
            for v in value
        )

    if wanted_type == tuple and isinstance(value, tuple): 
        # `Tuple`/`tuple` requires a type argument for each position
        return tuple(
            validate_and_instantiate(tt, v)
            for tt, v in zip(type_args, value)
        )

    if wanted_type == dict and isinstance(value, dict): 
        # `Dict`/`dict` requires 2 type arguments: one for keys, another for values
        k_type, v_type = type_args
        return {
            validate_and_instantiate(k_type, k) : validate_and_instantiate(v_type, v)
            for k, v in value.items()
        }
    
    raise ParsingError(f"Unhandled case! Could not parse type:{t}, value:{value}")

def interleave(list1: list, list2: list) -> list:
    out = [ ]

    while len(list1) > 0 or len(list2) > 0:
        if len(list1) > 0:
            out.append(list1.pop(0))
        if len(list2) > 0:
            out.append(list2.pop(0))

    return out

def submission_line_to_code(sub_line: Submission.Line) -> str:
    prefix = sub_line.indent * "    "
    code = prefix + "".join(interleave(sub_line.codeSnippets, sub_line.blankValues))
    return code

def submission_line_to_mustache(sub_line: Submission.Line, language: str) -> Mustache.Line:
    return Mustache.Line(
        indent=sub_line.indent,
        segments=[
            Mustache.Line.Segment(
                blank = Mustache.Line.Segment.Blank(
                        default=snippet,
                        width=max(4, len(snippet) + 1)
                    ) if i%2==1 else None,
                code = Mustache.Line.Segment.Code(
                        content=snippet,
                        language=language
                    ) if i%2==0 else None
            )
            for i, snippet in enumerate(interleave(sub_line.codeSnippets, sub_line.blankValues))
    ])

#
# The FPP Definition
#

class FadedParsonsProblem:
    """An instance of an FPP
    
    Instantiate an FPP from an html tag and populate the trays with
    either submitted state or the provided markup.

    XML Attributes
    --------------
    `answers-name="..."`  
        The unique identifier for this problem. Raises error if `ValueError` if empty or missing.  
    `format={ right | bottom | no-code }`  
        The provided format of the problem. Defaults to "right".  
    `language`  
        The language with which to apply syntax highlighting. Defaults to "" (no highlighting).  
    `file-name`  
        The file to store the student's submission for grading. Defaults to `user_code.py`.  
    `solution-path`  
        The path to a file containing the solution. Defaults to "./solution".  

    Attributes
    ----------
    `answers_name` : `str`
        This problem's identifier. Specified with `answers-name="..."`.
    `format` : `FadedParsonsProblem.Formats`
        The provided format of the problem. Specified with `format="..."`.
    `markup` : `str`
        The markup provided in html that is parsed into lines for the student. Is not used if the student has previously made a submission.
    `pre_text` : `str`
        The text that will be shown directly before the solution tray. Will be an empty string and not rendered if omitted. Cannot be used with format="right".
    `post_text` : `str`
        The text that will be shown directly after the solution tray. Will be an empty string and not rendered if omitted. Cannot be used with format="right".
    `language` : `str`
        The language with which to apply syntax highlighting. May be an empty string, in which case no highlighting will be done.
    `out_filename` : `str`
        The file to which to include the student's submission. Specified with `file-name="..."`.
    `size` : `Literal["narrow", "wide"]`
        The size of the solution tray. `"narrow"` indicates it should take approximately half the width of the problem pane. `"wide"` indicates it should take the full width of the problem pane.
    `solution_path` : `str`
        The path to a file containing the solution. Specified with `solution-path="..."`. Raises `FileNotFoundError` on access if not found.
    `solution` : `str`
        The solution. Specified with `solution-path="..."`. Raises `FileNotFoundError` on access if file not found.
    `trays` : `Submission.Trays`
        The trays used in this problem. MUST CALL `.load(...)` TO DEFINE.
    `log` : `List[Submission.LogEntry]`
        The log of events for this problem. MUST CALL `.load(...)` TO DEFINE.

    Methods
    -------
    `to_mustache() -> Mustache`
        Produce a `Mustache` instance for rendering
    `to_code() -> str`
        Compile the student submission into an executable code snippet.

    """

    class Formats(Enum):
        BOTTOM = "bottom"
        RIGHT = "right"
        NO_CODE = "no_code"

    @property
    def solution_path(self) -> str:
        if not os.path.exists(self._solution_path):
            raise FileNotFoundError('\n'
                f'\tCorrect answer not found at `{self._solution_path}`! \n'
                 '\tProvide an answer or set "showCorrectAnswer" to false in `./info.json`'
            )

        return self._solution_path

    @property
    def solution(self) -> str:
        with open(self.solution_path, "r") as f:
            return f.read()

    def __init__(self, element_html: str, data: pl.QuestionData):

        element: xml.HtmlElement = xml.fragment_fromstring(element_html)
        self._element: xml.HtmlElement = element
        pl.check_attribs(
            element,
            required_attribs=[
                "answers-name",
            ],
            optional_attribs=[
                "solution-path",
                "format",
                "language",
                "file-name",
                "solution-path"
            ]
        )

        self.answers_name: str = pl.get_string_attrib(element, 'answers-name', '')
        self.format = FadedParsonsProblem.Formats(
            pl.get_string_attrib(element, "format", "right")
                .replace("-", '_')
        )
        self.pre_text  = get_child_text_by_tag(element, "pre-text").strip("\n")
        self.post_text = get_child_text_by_tag(element, "post-text").strip("\n")
        self.language: str = pl.get_string_attrib(element, "language", "")
        self.out_filename = pl.get_string_attrib(element, 'file-name', 'user_code.py')
        self.size = "narrow" if self.format == FadedParsonsProblem.Formats.RIGHT else "wide"

        self.markup = get_child_text_by_tag(self._element, "code-lines")
        if not self.markup:
            try:
                path = os.path.join(self._options["question_path"], 'serverFilesQuestion', 'code_lines.txt')
                with open(path, 'r') as f:
                    self.markup = f.read()
            except:
                self.markup = str(self._element.text)

        if self.format == FadedParsonsProblem.Formats.RIGHT and (self.pre_text or self.post_text):
            raise Exception("pre-text and post-text are not supported in right (horizontal) mode. " +
                'Add/set `format="bottom"` or `format="no-code"` to your element to use this feature.')

        self._solution_path = pl.get_string_attrib(element, 'solution-path', './solution')
        self._max_distractors = 10 # this was hardcoded before
        self._raw_answers = data["raw_submitted_answers"]
        self._options = data["options"]
        self._load()

    def _load(self) -> None:
        if self.answers_name in self._raw_answers:
            prev_submission: Submission = cast(Submission, validate_and_instantiate(Submission, self._raw_answers[self.answers_name]))
            self._trays_from_submission(prev_submission)
        else:
            self._trays_from_markup()

    def _trays_from_markup(self) -> None:

        starters, givens, distractors = [], [], []
        BLANK = re.compile(r'#blank [^#]*')
        GIVEN = re.compile(r'#(\d+)given')
        DISTRACTOR = re.compile(r'#distractor')

        for raw_line in self.markup.strip().split('\n'):
            
            line_str = raw_line.strip()
            snippets = line_str.split("#")[0].split("!BLANK")

            blanks = [''] * (len(snippets) - 1)
            if blank_defaults := re.findall(BLANK, line_str):
                for i, val in enumerate(blank_defaults):
                    blanks[i] = val.replace('#blank', '').strip()


            if match := re.search(GIVEN, line_str):
                givens.append(Submission.Line(int(match.group(1)), snippets, blanks))
            else:

                line = Submission.Line(0, snippets, blanks)
                if re.search(DISTRACTOR, line_str):
                    distractors.append(line)
                else:
                    starters.append(line)

        distractor_count = min(len(distractors), self._max_distractors)
        starters.extend(random.sample(distractors, k=distractor_count))

        random.shuffle(starters)

        self.trays: Submission.Trays
        if format == FadedParsonsProblem.Formats.NO_CODE:
            self.trays = Submission.Trays(
                solution = givens + starters,
                starter = [ ]
            )
        else:
            self.trays = Submission.Trays(
                solution = givens,
                starter = starters
            )
        self.log: List[Submission.LogEntry] = [ ]

    def _trays_from_submission(self, data: Submission) -> None:
        self.trays: Submission.Trays = data.main
        self.log: List[Submission.LogEntry] = data.log

    def to_mustache(self) -> Mustache:
        if self.trays.starter in ([], None):
            starter_lines = ''
        else:
            starter_lines = Mustache.TrayLines(
                lines=[
                    submission_line_to_mustache(sub_line=l, language=self.language)
                    for l in self.trays.starter
                ]
            )

        return Mustache(
            answers_name=self.answers_name,
            language=self.language,
            previous_log=json.dumps(self.log),
            uuid=pl.get_uuid(),
            starter=starter_lines,
            pre_text=self.pre_text,
            given=Mustache.TrayLines(
                lines=[
                    submission_line_to_mustache(sub_line=l, language=self.language)
                    for l in self.trays.solution
                ]
            ),
            post_text=self.post_text
        )
    
    def to_code(self) -> str:
        return "\n".join(
            map(
                submission_line_to_code,
                self.trays.solution,
            )
        )

    def to_legacy_data(self) -> Dict[str, Any]:
        data: Dict[str, Any] = {
            "student-parsons-solution": self.to_code(),
            "submission-lines": [
                {
                    "content": submission_line_to_code(line),
                    "indent": line.indent,
                    "segments": {
                        "givenSegments": line.codeSnippets,
                        "blankValues": line.blankValues,
                    },
                    # "id": str, #$(line).attr("logging-id"),
                    # "index": int,
                }
                for line in self.trays.solution
            ]
        }

        if self.format != FadedParsonsProblem.Formats.NO_CODE:
            assert self.trays.starter is not None # to appease the typechecker

            data["starter-lines"] = [
                {
                    "content": submission_line_to_code(line),
                    "indent": line.indent,
                    "segments": {
                        "givenSegments": line.codeSnippets,
                        "blankValues": line.blankValues,
                    },
                    # "id": str, #$(line).attr("logging-id"),
                    # "index": int,
                }
                for line in self.trays.starter
            ]

        return data


#
# Main functions
#
def render(element_html: str, data: pl.QuestionData):
    panel_type = data['panel']

    fpp = FadedParsonsProblem(element_html, data)
    mustache_file = f'pl-faded-parsons-{panel_type}.mustache'

    if panel_type == 'question':
        # chevron skips rendering when values are falsy (eg pre-text/post-text/starter)
        html_params = asdict(fpp.to_mustache())
    elif panel_type == 'submission':
        html_params = {
            'code': fpp.to_code(),
        }
    elif panel_type == 'answer':
        html_params = {
            "solution_path": fpp.solution_path
        }
    else:
        raise Exception(f'Invalid panel type: {panel_type}')

    with open(mustache_file, 'r') as f:
        return chevron.render(f, html_params).strip()


def parse(element_html: str, data: pl.QuestionData):
    """Parse student's submitted answer (HTML form submission)"""
    def base64_encode(s):
        return base64.b64encode(s.encode("ascii")).decode("ascii")

    fpp = FadedParsonsProblem(element_html, data)

    student_code = fpp.to_code()

    # provide the answer to users of pl-faded-parsons in classic PL style    
    data['submitted_answers'][fpp.answers_name] = student_code
    pl.add_submitted_file(data, fpp.out_filename, base64_encode(student_code))
    
    # support legacy questions from when we wrote to the wrong place
    data['submitted_answers'].update(fpp.to_legacy_data())
