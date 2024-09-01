try:
    import prairielearn as pl
except ModuleNotFoundError:
    print('<!> pl not loaded! <!>')

from typing import Union, List, Dict
from datetime import datetime
from enum import StrEnum

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

@dataclass(frozen=True, slots=True)
class Submission:
    '''
    Represent the contents of input.main and input.log from pl-faded-parsons-question.mustache
    '''

    @dataclass(frozen=True, slots=True)
    class Line:
        indent: int
        codeSnippets: list[str]
        blankValues: list[str]

        def __post_init__(self):
            if len(self.codeSnippets) != len(self.blankValues) + 1:
                raise ValueError('codeSnippets must have one more element than blankValues')

    @dataclass(frozen=True, slots=True)
    class Trays:
        solution: List["Submission.Line"]
        starter: Union[List["Submission.Line"], None] = None

    @dataclass(frozen=True, slots=True)
    class LogEntry:
        timestamp: datetime
        tag: str # this is technically an enum of string literals ... Maybe enumerate eventually?
        data: dict # TODO: expand this, the "tag" tells us the type of JSON object this is

    main: Trays
    log: List[LogEntry] = field(default_factory=list)

@dataclass(frozen=True, slots=True)
class Mustache:

    @dataclass(frozen=True, slots=True)
    class Line:

        @dataclass(frozen=True, slots=True)
        class CodeSegment:
            @dataclass(frozen=True, slots=True)
            class InnerData:
                content: str
                language: str
            
            code: InnerData
            # { 'code': { 'content': value, 'language': language } }

        @dataclass(frozen=True, slots=True)
        class BlankSegment:
            @dataclass(frozen=True, slots=True)
            class InnerData:
                default: str
                width: str # max(4, len(value) + 1)
            
            blank: InnerData
            # { 'blank': { 'default': value, 'width': max(4, len(value) + 1) } }

        indent: int
        segments: List[Union[CodeSegment, BlankSegment]]

    @dataclass(frozen=True, slots=True)
    class TrayLines:
        lines: List[Mustache.Line] # [Line.to_mustache(l, lang) for l in lines]
        size: bool = True # any truthy value will do

    # chevron skips rendering when values are falsy (eg pre-text/post-text/starter)

    # main element config
    answers_name : str
    language : str
    previous_log : str
    uuid: pl.get_uuid()

    # trays and code context
    starter: Union[TrayLines, Literal[[]]] = field(default_factory=list)
    pre_text: str
    given: TrayLines
    post_text: str

class FadedParsonsProblem:
    """A mutable instance of an FPP
    
    Instantiate an FPP from an html tag and populate the trays with
    either submitted state or the provided markup.

    Attributes
    ----------
    `answers_name` : `str`
        This problem's identifier. Specified with `answers-name="..."`. Raises error if `ValueError` if empty.
    `format` : `FadedParsonsProblem.Formats`
        The provided format of the problem. Specified with `format="..."`. Defaults to "right".
    `pre_text` : `str`
        The text that will be shown directly before the solution tray. Will be an empty string if omitted. Cannot be used with format="right".
    `post_text` : `str`
        The text that will be shown directly after the solution tray. Will be an empty string if omitted. Cannot be used with format="right".
    `language` : `str`
        The language to pass on for syntax highlighting.
    `out_filename` : `str`
        The file to which to include the student's submission. Specified with `file-name="..."`. Defaults to `user_code.py`.
    `size` : `Literal["narrow", "wide"]`
        The size of the solution tray. `"narrow"` indicates it should take approximately half the width of the problem pane. `"wide"` indicates it should take the full width of the problem pane.
    `solution` : `str`
        The solution. Specified with `solution-path="./relative/path/to/solution"`. Raises `FileNotFoundError` on access if not found. Defaults to `./solution`.
    `trays` : `Submission.Trays`
        The trays used in this problem. MUST CALL `.load(...)` TO DEFINE.
    `log` : `List[Submission.LogEntry]`
        The log of events for this problem. MUST CALL `.load(...)` TO DEFINE.

    Methods
    -------
    ...

    """

    class Formats(StrEnum):
        BOTTOM = "bottom"
        RIGHT = "right"
        NO_CODE = "no_code"

    @property
    def solution() -> str:
        if not os.path.exists(self._solution_path):
            raise FileNotFoundError('\n'
                f'\tCorrect answer not found at `{self.solution_path}`! \n'
                 '\tProvide an answer or set "showCorrectAnswer" to false in `./info.json`'
            )

        with open(self._solution_path, "r") as f:
            return f.read()

    def __init__(self, element_html):

        def get_child_text_by_tag(element, tag: str) -> str:
            """get the innerHTML of the first child of `element` that has the tag `tag`
            default value is empty string"""
            return next((elem.text for elem in element if elem.tag == tag), "")

        element = xml.fragment_fromstring(element_html)
        self._element = element
        self._solution_path = pl.get_string_attrib(element, 'solution-path', './solution')

        self.answers_name: str = pl.get_string_attrib(element, 'answers-name', '')
        if self.answers_name == "":
            raise ValueError() # FIXME: fill error message

        self.format = FadedParsonsProblem.Formats(
            pl.get_string_attrib(element, "format", "right")
                .replace("-", '_')
        )

        self.pre_text  = get_child_text_by_tag(element, "pre-text").strip("\n")
        self.post_text = get_child_text_by_tag(element, "post-text").strip("\n")

        self.language: str | None = pl.get_string_attrib(element, "language", None)
        self.out_filename = pl.get_string_attrib(element, 'file-name', 'user_code.py')

        self.size = "narrow" if self.format == FadedParsonsProblem.Formats.RIGHT else "wide"

        if self.format == FadedParsonsProblem.Formats.RIGHT and pre_text or post_text:
            raise Exception("pre-text and post-text are not supported in right (horizontal) mode. " +
                'Add/set `format="bottom"` or `format="no-code"` to your element to use this feature.')

    def load(self, raw_answers) -> None:
        if self.answers_name in raw_answers:
            prev_submission: Submission = recursive_instantiate(Submission, raw_answers[fpp.answers_name])
            self._trays_from_submission(prev_submission)
        else:
            self._trays_from_markup()

    def _trays_from_markup(self) -> None:
        if not (markup := get_child_text_by_tag(self._element, "code-lines")):
            try:
                path = os.path.join(data["options"]["question_path"], 'serverFilesQuestion', 'code_lines.txt') # TODO: fix dict accessing
                with open(path, 'r') as f:
                    markup = f.read()
            except:
                markup = str(self._element.text)

        BLANK = re.compile(r'#blank [^#]*')
        GIVEN = re.compile(r'#(\d+)given')
        DISTRACTOR = re.compile(r'#distractor')

        starters, givens, distractors = [], [], []
        for raw_line in markup.strip().split('\n'):
            
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

        distractor_count = min(len(distractors), max_distractors)
        starters.extend(random.sample(distractors, k=distractor_count))

        random.shuffle(starters)

        self.trays: Submission.Trays
        if format == 'no_code':
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

    def to_mustache() -> Mustache:
        return Mustache(
            answers_name=self.answers_name,
            language=self.language,
            previous_log=json.dumps(self.log),
            uuid=pl.get_uuid(),
            starter=Mustache.TrayLines(
                ...
            ),
            pre_text=self.pre_text,
            given=Mustache.TrayLines(
                lines=...
            ),
            post_text=self.post_text
        )
    
    def to_code() -> str:
        raise NotImplementedError("AAAGGGGHHHH! I FORGOT TO DO THIS!!!")
        f"""
        ...
        """


#
# Main functions
#
def render(element_html, data):
    panel_type = data['panel']

    fpp = FadedParsonsProblem(element_html)
    fpp.load(data['raw_submitted_answers'])
    filename = f'pl-faded-parsons-{panel_type}.mustache'

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

    with open('pl-faded-parsons-question.mustache', 'r') as f:
        return chevron.render(f, html_params).strip()


def parse(element_html, data):
    """Parse student's submitted answer (HTML form submission)"""
    def base64_encode(s):
        return base64.b64encode(s.encode("ascii")).decode("ascii")

    fpp = FadedParsonsProblem(element_html)
    fpp.load(data['raw_submitted_answers'])

    student_code = fpp.to_code()

    data['submitted_answers'].update(submission.to_pl_data())
    data['submitted_answers'].update({
        '_files': [
            {
                "name": fpp.out_filename,
                "contents": base64_encode(student_code)
            }
        ],
        # provide the answer to users of pl-faded-parsons in classic PL style
        answers_name: student_code,
    })
