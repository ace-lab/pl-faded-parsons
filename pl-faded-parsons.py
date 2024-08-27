try:
    import prairielearn as pl
except ModuleNotFoundError:
    print('<!> pl not loaded! <!>')

import base64
import chevron
import itertools
import json
import os.path
import random
import typing
import lxml.html as xml

from abc import ABC, abstractmethod
from dataclasses import dataclass


#
# Common Datatypes for Parsing External Data
#
class Mustachable(ABC):
    'An interface for classes that export to .mustache'
    @abstractmethod
    def to_mustache(self, language) -> dict:
        pass


@dataclass(frozen=True, slots=True)
class Segment(Mustachable, ABC):
    '''
    Segments match what is used in pl-faded-parsons-code-line.mustache:
    ``` ts
    type Segment =
        | { code: { content: string, language: string } }
        | { blank: { default: string, width: number } };
    ```
    '''
    value: str

    def get_text(self):
        return self.value


class BlankSegment(Segment):
    def to_mustache(self, _):
        width = max(len(self.value) + 1, 4)
        return { "blank" : { "default" : self.value, "width": width } }


class CodeSegment(Segment):
    def to_mustache(self, language):
        return { "code" : { "content" : self.value, "language": language } }


@dataclass(frozen=True, slots=True)
class Line(Mustachable):
    '''
    A helper class for reading, storing, and writing common line data.

    Import/export uses the schema in pl-faded-parsons.js `codelineSummary`.
    Expects a line to have the type:
    ``` ts
    type CodelineSummary = {
        indent: number,
        segments: { givenSegments: string[], blankValues: string[], },
        content: string,
    };
    ```
    where `givenSegments.length() == 1 + blankValues.length()`
    '''
    indent: int
    segments: list[Segment]
    content: str | None = None

    @staticmethod
    def _import(line: dict) -> 'Line':
        # from pl-faded-parsons.js `codelineSummary` and `getCodelineSegments`
        indent = line.get('indent', 0)
        segments = code_and_blanks_to_segments(
            line['segments']['givenSegments'], line['segments']['blankValues']
        )
        content = line.get('content', None)
        return Line(indent, segments, content)

    def _export(self) -> dict:
        def text_list(ls): return list(map(Segment.get_text, ls))
        given = text_list(self.segments[0::2])
        blank = text_list(self.segments[1::2])
        return {
            "indent": self.indent,
            "segments": { "givenSegments": given, "blankValues": blank },
            "content": self.content,
        }

    def to_mustache(self, language, *, indent_size=4) -> dict:
        return {
            "indent": self.indent * indent_size,
            "segments": [s.to_mustache(language) for s in self.segments]
        }

    def get_text(self) -> str:
        if self.content is not None: return self.content
        ind = self.indent * ' '
        return ind + ''.join(map(Segment.get_text, self.segments))


@dataclass(frozen=True, slots=True)
class Submission:
    '''
    Record that loads submission data from the PL `data` param. Save locations
    set by the `input` elements in pl-faded-parsons-question.mustache.
    `answers_name` is the problem name passed in the `element_html`.
    '''
    answers_name: str
    starter_lines: list[Line]
    solution_lines: list[Line]
    log: list[dict]

    @staticmethod
    def make_key(answers_name, input_name): return f'{answers_name}.{input_name}'

    @staticmethod
    def _import(answers_name: str, answers_data: dict):
        'works for `data["raw_submitted_answers"]` and `data["submitted_answers"]`'
        def load_input_field(input_name, default):
            k = Submission.make_key(answers_name, input_name)
            v = answers_data.get(k, default)
            return json.loads(v) if type(v) is str else v

        def import_lines(mem: dict, entry: str):
            return [Line._import(l) for l in mem.get(entry, [])]

        main_memory = load_input_field('main', {})

        return Submission(
            answers_name,
            import_lines(main_memory, 'starter'),
            import_lines(main_memory, 'solution'),
            load_input_field('log', []),
        )

    def _export(self) -> dict[str, str]:
        main_mem = {
            'starter': [l._export() for l in self.starter_lines],
            'solution': [l._export() for l in self.solution_lines],
        }
        return {
            Submission.make_key(self.answers_name, 'main'): json.dumps(main_mem),
            Submission.make_key(self.answers_name, 'log'): json.dumps(self.log),
        }

    def get_student_code(self):
        if not self.solution_lines: return ''
        return '\n'.join(map(Line.get_text, self.solution_lines)) + '\n'

    def __bool__(self):
        return bool(self.solution_lines or self.starter_lines)


#
# Helper functions
#
def alternate(xs: typing.Iterable, ys: typing.Iterable):
    'alternates between `xs` and `ys` until an empty iter would be polled'
    iters, stop = itertools.cycle((iter(xs), iter(ys))), object()
    while (x := next(next(iters), stop)) is not stop:
        yield x


def code_and_blanks_to_segments(code_snippets, blank_values) -> list[dict]:
    'generates a list of segments by interleaving the code snippets and blank values'
    code_segments  = map(CodeSegment,  code_snippets)
    blank_segments = map(BlankSegment, blank_values)
    return list(alternate(code_segments, blank_segments))


def get_answers_name(element):
    'answers-name namespaces answers for multiple elements on a page'
    return pl.get_string_attrib(element, 'answers-name', '')


def parse_new_state(raw_lines, *, max_distractors=10) -> tuple[list[Line], list[Line]]:
    import re

    blank_pattern = re.compile(r'#blank [^#]*')
    given_pattern = re.compile(r'#(\d+)given')

    def get_blank_values(segments):
        values = [''] * (len(segments) - 1)
        for i, e in enumerate(re.findall(blank_pattern, segments[-1])):
            values[i] = e.replace('#blank', '').strip()
        return values

    def parse_line(line: str) -> tuple[list[dict], str]:
        segments = line.strip().split('!BLANK')

        # get the starting placeholder text, then remove those special comments
        blanks = get_blank_values(segments)
        tail = segments[-1] = re.sub(blank_pattern, '', segments[-1])

        return code_and_blanks_to_segments(segments, blanks), tail

    split_lines = raw_lines.strip().split('\n')
    parsed_lines = map(parse_line, split_lines)

    # clean, mint, and sort the lines based on special comments
    starter, given, distractors = [], [], []
    for segments, tail in parsed_lines:
        indent = 0

        if matches := re.search(given_pattern, tail):
            indent = int(matches.group(1))
            segments[-1] = CodeSegment(re.sub(given_pattern, '', tail).rstrip())
            target = given
        elif '#distractor' in tail:
            segments[-1] = CodeSegment(tail.replace('#distractor', '').rstrip())
            target = distractors
        else:
            target = starter

        target.append(Line(indent, segments))

    distractor_count = min(len(distractors), max_distractors)
    starter.extend(random.sample(distractors, k=distractor_count))

    return starter, given


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

    def load_new_state(element, *, shuffle_solution):
        raw_lines = get_child_text_by_tag(element, "code-lines")

        if not raw_lines:
            try:
                path = os.path.join(data["options"]["question_path"], 'serverFilesQuestion', 'code_lines.txt')
                with open(path, 'r') as f:
                    raw_lines = f.read()
            except:
                raw_lines = str(element.text)

        starter_lines, solution_lines = parse_new_state(raw_lines)

        random.shuffle(starter_lines)
        if shuffle_solution:
            random.shuffle(solution_lines)

        return starter_lines, solution_lines

    def get_current_state(element, past_submission: Submission, separate_starter: bool):
        if past_submission:
            starter_lines, solution_lines = \
                submission.starter_lines, submission.solution_lines
        else:
            starter_lines, solution_lines = \
                load_new_state(element, shuffle_solution=not separate_starter)

        if not separate_starter:
            return None, solution_lines + starter_lines

        return starter_lines, solution_lines

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

    submission = Submission._import(answers_name, data['submitted_answers'])
    starter_lines, given_lines = get_current_state(element, submission, use_starter_tray)

    tray_lines_to_mustache = lambda lines: {
        "lines": [Line.to_mustache(l, lang) for l in lines],
        size: True # any truthy value will do
    }

    # chevron skips rendering when values are falsy (eg pre-text/post-text/starter)
    html_params = {
        # main element config
        "answers-name": answers_name,
        "language": lang,
        "previous-log" : json.dumps(submission.log),
        "uuid": pl.get_uuid(),

        # trays and code context
        "starter": use_starter_tray and tray_lines_to_mustache(starter_lines),
        "pre-text": pre_text,
        "given": tray_lines_to_mustache(given_lines),
        "post-text": post_text,
    }

    with open('pl-faded-parsons-question.mustache', 'r') as f:
        return chevron.render(f, html_params).strip()


def render_submission_panel(element_html, data):
    """Show student what they submitted"""
    element = xml.fragment_fromstring(element_html)
    answers_name = get_answers_name(element)
    submission = Submission._import(answers_name, data['submitted_answers'])
    html_params = {
        'code': submission.get_student_code(),
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

    submission = Submission._import(answers_name, data['raw_submitted_answers'])

    data['submitted_answers'].update({
        '_files': [
            {
                "name": file_name,
                "contents": base64_encode(submission.get_student_code())
            }
        ],
        # provide the answer to users of pl-faded-parsons in classic PL style
        answers_name: submission.get_student_code(),
        **submission._export()
    })
