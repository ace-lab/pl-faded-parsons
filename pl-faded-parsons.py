import prairielearn as pl
import lxml.html as xml
import chevron
import os
import base64
import json


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


def get_answers_name(element_html):
    # use answers-name to namespace multiple pl-faded-parsons elements on a page
    element = xml.fragment_fromstring(element_html)
    answers_name = pl.get_string_attrib(element, 'answers-name', None)
    if answers_name is not None:
        answers_name = answers_name + '-'
    else:
        answers_name = ''
    return answers_name


def get_student_code(element_html, data):
    answers_name = get_answers_name(element_html)
    student_code = data['submitted_answers'].get(answers_name + 'student-parsons-solution', None)
    return student_code


def base64_encode(s):
    return base64.b64encode(s.encode("ascii")).decode("ascii")


def render_question_panel(element_html, data):
    """Render the panel that displays the question (from code_lines.txt) and interaction boxes"""
    element = xml.fragment_fromstring(element_html)
    answers_name = get_answers_name(element_html)

    format = pl.get_string_attrib(element, "format", "right").replace("-", '_')
    if format not in ("bottom", "right", "no_code"):
        raise Exception(f"Unsupported pl-faded-parsons format: \"{format}\". Please see documentation for supported formats")

    lang = pl.get_string_attrib(element, "language", None)

    populate_info = []
    for blank in data['submitted_answers']:
        if blank[0:24] == 'parsons-solutioncodeline':
            populate_info.append({'name': blank, 'value': data['submitted_answers'][blank]})

    student_order_info = json.loads(data['submitted_answers']['starter-code-order']) if 'starter-code-order' in data['submitted_answers'] else []
    solution_order_info = json.loads(data['submitted_answers']['parsons-solution-order']) if 'parsons-solution-order' in data['submitted_answers'] else []

    html_params = {
        "code_lines": str(element.text),
        "populate_info": populate_info,
        "student_order_info": student_order_info,
        "solution_order_info": solution_order_info,
        format : {
            "answers_name": answers_name,
        }
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

    pre_text = get_child_text_by_tag(element, "pre-text") \
        .rstrip("\n") # trim trailing newlines
    post_text = get_child_text_by_tag(element, "post-text") \
        .lstrip("\n") # trim leading newlines

    pre = { "text" : pre_text }
    post = { "text" : post_text}

    if lang:
        pre.update({ "language" : f"language=\"{lang}\"" })
        post.update({ "language" : f"language=\"{lang}\"" })

    if pre_text:
        html_params[format].update({ 
            "pre_text" : pre,
        })
    if post_text:
        html_params[format].update({
            "post_text" : post,
        })

    if format == "right":
        if pre_text or post_text:
            raise Exception("pre-text and post-text are not supported in right (horizontal) mode. " +
                'Add format="bottom" to your element to use this feature.')
        
    if format == "bottom":
        if pre_text or post_text:
            html_params.update({ "code_lines" : get_code_lines() })


    with open('pl-faded-parsons-question.mustache', 'r') as f:
        return chevron.render(f, html_params).strip()

def render_submission_panel(element_html, data):
    """Show student what they submitted"""
    html_params = {
        'code': get_student_code(element_html, data),
    }
    with open('pl-faded-parsons-submission.mustache', 'r') as f:
        return chevron.render(f, html_params).strip()


def render_answer_panel(element_html, data):
    """Show the instructor's reference solution"""
    html_params = {
        "solution_path": "solution",
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
    # make an XML fragment that can be passed around to other PL functions,
    # parsed/walked, etc
    element = xml.fragment_fromstring(element_html)

    # `element` is now an XML data structure - see docs for LXML library at lxml.de

    # only Python problems are allowed right now (lang MUST be "py")
    # lang = pl.get_string_attrib(element, 'language') # TODO: commenting is a stop gap for the pilot study, find a better solution

    file_name = pl.get_string_attrib(element, 'file-name', 'user_code.py')

    data['submitted_answers']['_files'] = [
        {
            "name": file_name,
            "contents": base64_encode(get_student_code(element_html, data))
        }
    ]

    # TBD do error checking here for other attribute values....
    # set data['format_errors']['elt'] to an error message indicating an error with the
    # contents/format of the HTML element named 'elt'
    return


def grade(element_html, data):
    """ Grade the student's response; many strategies are possible, but none are necessary.
        This is externally autograded by a custom library.
    """
    pass