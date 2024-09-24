import prairielearn as pl
import lxml.html as xml
import chevron
import os
import base64
import json
import re
import random


#
# Helper functions
#
def read_file_lines(data, filename, error_if_not_found=True):
    """Return a string of newline-separated lines of code from some file in serverFilesQuestion."""
    path = os.path.join(data["options"]["question_path"], 'serverFilesQuestion', filename)
    try:
        f = open(path, 'r')
        return f.read()
    except FileNotFoundError as e:
        if error_if_not_found:
            raise e
        else:
            return False


def get_student_code(element, data):
    answers_name = pl.get_string_attrib(element, 'answers-name')
    student_code = data['submitted_answers'].get(answers_name + 'student-parsons-solution', None)
    return student_code


def parse_lines(language, lines):
    'Reads lines structured by pl-faded-parsons.js codelineSummary'
    for line in lines:
        old_segments = line['segments']['givenSegments']
        segments = [{ "code" : { "content" : old_segments[0] }}]

        for segment, fill in zip(old_segments[1:], line['segments']['blankValues']):
            segments.append({ "blank" : { "default" : fill    }})
            segments.append({ "code"  : { "content" : segment }})

        yield {
            "language" : language,
            "segments" : segments,
            "indent": line.get('indent', 0)
        }


def load_previous_state(language, old_starter, old_submission, indent_size=4):
    scrambled = list(parse_lines(language, old_starter))
    given = []

    for data in parse_lines(language, old_submission):
        data['indent'] *= indent_size
        given.append(data)

    return scrambled, given


def load_starter_and_given(raw_lines, language, indent_size=4, max_distractors=10):
    line_segments = [ line.strip().split('!BLANK') for line in raw_lines.strip().split('\n') ]

    scrambled = []
    given = []
    distractors = []

    for segments in line_segments:
        new_line = { "language": language }

        matches = re.findall(r'#blank [^#]*', segments[-1])
        tail = re.sub(r'#blank [^#]*', '', segments[-1])
        blank_count = len(segments) - 1
        fills = list(map(lambda e: e.replace('#blank ', ""), matches)) + [""] * (blank_count-len(matches))
        segments[-1] = tail

        parsed_segments = [{ "code" : { "content" : segments[0] } }]
        for segment, pre_fill in zip(segments[1:], fills):
            width = str(len(pre_fill)+1) if pre_fill != "" else "4"
            parsed_segments.append({ "blank" : { "default" : pre_fill, "width" : width } })
            parsed_segments.append({ "code"  : { "content" : segment  } })

        matches = re.search(r'#([0-9]+)given', tail)
        if matches is not None:
            indent = int(matches.group(1))
            new_line['indent'] = indent * indent_size
            parsed_segments[-1] = {
                "code" : { "content" : re.sub(r'#([0-9]+)given', '', tail).rstrip() }
            }
            new_line['segments'] = parsed_segments
            given.append(new_line)
            continue

        if re.match(r'#distractor', tail):
            parsed_segments[-1] = {
                "code" : { "content" : re.sub(r'#distractor', '', tail).rstrip() }
            }
            new_line['segments'] = parsed_segments
            distractors.append(new_line)
            continue

        new_line['segments'] = parsed_segments
        scrambled.append(new_line)


    for _ in range(max_distractors):
        if len(distractors) == 0:
            break
        index = random.randint(len(distractors))
        scrambled.append(distractors.pop(index))

    return scrambled, given


def base64_encode(s):
    return base64.b64encode(s.encode("ascii")).decode("ascii")


def render_question_panel(element, data):
    """Render the panel that displays the question (from code_lines.txt) and interaction boxes"""
    answers_name = pl.get_string_attrib(element, 'answers-name')

    format = pl.get_string_attrib(element, "format", "right").replace("-", '_')
    if format not in ("bottom", "right", "no_code"):
        raise Exception(f"Unsupported pl-faded-parsons format: \"{format}\". Please see documentation for supported formats")

    lang = pl.get_string_attrib(element, "language", None)

    html_params = {
        "code_lines": str(element.text),
    }

    def get_child_text_by_tag(element, tag: str) -> str:
        """get the innerHTML of the first child of `element` that has the tag `tag`
        default value is empty string"""
        return next((elem.text for elem in element if elem.tag == tag), "")

    def get_code_lines():
        code_lines = get_child_text_by_tag(element, "code-lines") or \
            read_file_lines(data, 'code_lines.txt', error_if_not_found=False)

        if not code_lines:
            raise Exception("A non-empty code_lines.txt or <code-lines> child must be provided in right (horizontal) placement.")

        return code_lines

    # pre + post text
    pre_text = get_child_text_by_tag(element, "pre-text") \
        .strip("\n") # trim newlines
    post_text = get_child_text_by_tag(element, "post-text") \
        .strip("\n") # trim newlines

    pre  = { "text" : pre_text  }
    post = { "text" : post_text }

    if lang:
        pre.update({ "language" : lang })
        post.update({ "language" : lang })

    if pre_text:
        html_params.update({
            "pre_text" : pre,
        })
    if post_text:
        html_params.update({
            "post_text" : post,
        })

    try:
        raw_lines = get_code_lines()
    except:
        raw_lines = str(element.text)


    starter_lines    = data['submitted_answers'].get(answers_name + 'starter-lines', [])
    submission_lines = data['submitted_answers'].get(answers_name + 'submission-lines', [])

    if starter_lines or submission_lines:
        scrambled_lines, solution_lines = load_previous_state(lang, starter_lines, submission_lines)
    else:
        starter_lines, given_lines = load_starter_and_given(raw_lines, lang)
        scrambled_lines = starter_lines.copy()
        solution_lines = given_lines.copy()

        if format in ("right", "bottom", "no_code", ):
            random.shuffle(scrambled_lines)

    scrambled = { "lines" : scrambled_lines, "answers_name" : answers_name }
    given     = { "lines" : solution_lines , "answers_name" : answers_name }

    if format == "right":
        if pre_text or post_text:
            raise Exception("pre-text and post-text are not supported in right (horizontal) mode. " +
                'Add/set `format="bottom"` or `format="no-code"` to your element to use this feature.')
        size = "narrow"
    elif format == "bottom":
        size = "wide"
    elif format == "no_code":
        size = "wide"
        given["lines"] = given['lines'] + scrambled['lines']

    scrambled[size] = {"non_empty" : "non_empty"}
    given    [size] = {"non_empty" : "non_empty"}

    if format != "no_code":
        html_params.update({
            "scrambled" : scrambled,
        })
    html_params.update({
        "answers-name": answers_name,
        "given" : given,
        "uuid": pl.get_uuid(),
        "previous_log" : data['submitted_answers'].get(answers_name + 'log', "[]")
    })

    with open('pl-faded-parsons-question.mustache', 'r') as f:
        return chevron.render(f, html_params).strip()


def render_submission_panel(element, data):
    """Show student what they submitted"""
    html_params = {
        'code': get_student_code(element, data),
    }
    with open('pl-faded-parsons-submission.mustache', 'r') as f:
        return chevron.render(f, html_params).strip()


def render_answer_panel(element, data):
    """Show the instructor's reference solution"""
    path = pl.get_string_attrib(element, 'solution-path', './solution')
    path = os.path.join(data["options"]["question_path"], path)

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
    element = xml.fragment_fromstring(element_html)
    pl.check_attribs(
        element,
        required_attribs=["answers-name"],
        optional_attribs=["language", "format", "solution-path", "file-name"]
    )
    panel_type = data['panel']
    if panel_type == 'question':
        return render_question_panel(element, data)
    elif panel_type == 'submission':
        return render_submission_panel(element, data)
    elif panel_type == 'answer':
        return render_answer_panel(element, data)
    else:
        raise Exception(f'Invalid panel type: {panel_type}')


def parse(element_html, data):
    """Parse student's submitted answer (HTML form submission)"""
    element = xml.fragment_fromstring(element_html)
    format = pl.get_string_attrib(element, "format", "right").replace("-", '_')
    answers_name = pl.get_string_attrib(element, 'answers-name')

    def load_json_if_present(key: str, default=[]):
        if key in data['raw_submitted_answers']:
            return json.loads(data['raw_submitted_answers'][key])
        return default

    if format != "no_code":
        starter_lines = load_json_if_present(answers_name + 'starter-tray-order')
    submission_lines = load_json_if_present(answers_name + 'solution-tray-order')

    submission_code = "\n".join(
        line.get("content", "") for line in submission_lines
    ) + "\n"

    data['submitted_answers'][answers_name + 'student-parsons-solution'] = submission_code
    if format != "no_code":
        data['submitted_answers'][answers_name + 'starter-lines'] = starter_lines
    data['submitted_answers'][answers_name + 'submission-lines'] = submission_lines

    # `element` is now an XML data structure - see docs for LXML library at lxml.de

    # only Python problems are allowed right now (lang MUST be "py")
    # lang = pl.get_string_attrib(element, 'language') # TODO: commenting is a stop gap for the pilot study, find a better solution

    file_name = pl.get_string_attrib(element, 'file-name', 'user_code.py')

    data['submitted_answers']['_files'] = [
        {
            "name": file_name,
            "contents": base64_encode(get_student_code(element, data))
        }
    ]

    # TBD do error checking here for other attribute values....
    # set data['format_errors']['elt'] to an error message indicating an error with the
    # contents/format of the HTML element named 'elt'
