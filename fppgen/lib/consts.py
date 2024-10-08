from typing import Final
from re import compile, Pattern
import os.path

class Bcolors:
    # https://stackoverflow.com/questions/287871/how-to-print-colored-text-to-the-terminal
    HEADER: Final[str] = '\033[95m'
    OK_BLUE: Final[str] = '\033[94m'
    OK_CYAN: Final[str] = '\033[96m'
    OK_GREEN: Final[str] = '\033[92m'
    WARNING: Final[str] = '\033[93m'
    FAIL: Final[str] = '\033[91m'
    END_COLOR: Final[str] = '\033[0m'
    BOLD: Final[str] = '\033[1m'
    UNDERLINE: Final[str] = '\033[4m'

    @staticmethod
    def f(color: str, *args, sep=' '):
        return color + sep.join(map(str, args)) + Bcolors.END_COLOR

    @staticmethod
    def printf(color: str, *args, **kwargs):
        sep = ' '
        if 'sep' in kwargs:
            sep = kwargs['sep']
            del kwargs['sep']
        print(Bcolors.f(color, *args, sep=sep), **kwargs)

    @staticmethod
    def ok(*args, **kwargs):
        Bcolors.printf(Bcolors.OK_GREEN, *args, **kwargs)

    @staticmethod
    def warn(*args, **kwargs):
        Bcolors.printf(Bcolors.WARNING, *args, **kwargs)

    @staticmethod
    def fail(*args, **kwargs):
        Bcolors.printf(Bcolors.FAIL, *args, **kwargs)

    @staticmethod
    def info(*args, **kwargs):
        Bcolors.printf(Bcolors.OK_BLUE, *args, **kwargs)


TEMPLATE_DIRECTORY = os.path.join(os.path.dirname(__file__), 'template')

def read_template(path):
    with open(os.path.join(TEMPLATE_DIRECTORY, path), 'r') as f:
        return f.read()

TEST_DEFAULT: Final[str] = read_template('test.py')

SETUP_CODE_DEFAULT: Final[str] = read_template('setup.py')

SERVER_DEFAULT: Final[str] = read_template('server.py')

# Matches, with precedence in listed order:
MAIN_PATTERN: Final[Pattern] = compile('|'.join((
    # - capture group 0: (one-line) region delimiter surrounded by ##'s
    #                    (capturing only the text between the ##'s).
    #                    Consumes leading newline and surrounding spaces/tabs,
    #                    and if the next line doesn't have a region comment,
    #                    it consumes the trailing newline as well.
    r'(?:\r?\n|^)[\t ]*##[\t ]+(\S.*?)[\t ]+##.*?(?:(?=\r?\n[\t ]*##[^#])|\r?\n|$)',
    # - capture group 1:  (one-line) comment, up to next comment or newline
    #                     (excluding the newline/eof)
    r'(#.*?)(?=#|\r?\n|$)',
    # - capture group 2:
    #     - (multi-line) triple-apostrophe string literal
    #     - (multi-line) triple-quote string literal
    r'(\'\'\'[\s\S]*?\'\'\'|\"\"\"[\s\S]*?\"\"\")',  # [\s\S] includes newlines! don't change!
    # - capture group 3:
    #     - (one-line) single-backtick string literal
    #     - (one-line) single-apostrophe string literal
    #     - (one-line) single-quote string literal
    r'(\`.*?\`|\'.*?\'|\".*?\")'
)))

SPECIAL_COMMENT_PATTERN: Final[Pattern] = compile(
    r'^#(blank[^#]*|\d+given)'
)

DEFAULT_BLANK_PATTERN: Final[Pattern] = compile(r'\?([^?\n]*)\?')
BLANK_SUBSTITUTE: Final[str] = '!BLANK'

REGION_IMPORT_PATTERN: Final[Pattern] = compile(
    r'^\s*import\s*(.+?)\s+as\s+(.+?)\s*$'
)

PROGRAM_DESCRIPTION: Final[str] = Bcolors.f(Bcolors.OK_GREEN, ' A tool for generating faded parsons problems.') + """

 Provide the path to well-formatted python file(s), and a question template will be generated.
 This tool will search for a path in ./ questions/ ../../questions/ and ../../ before erring.
 If none is provided, it will hunt for a questions directory, and use all .py files there.
 """ + Bcolors.f(Bcolors.OK_BLUE, 'Formatting rules:') + """
 - If the file begins with a docstring, it will become the question text
     - The question text is removed from the answer
     - Docstrings are always removed from the prompt
 - Text surrounded by `?`s will become blanks in the prompt
     - Blanks cannot span more than a single line
     - The text within the question marks fills the blank in the answer
     - `?`s in any kind of string-literal or comment are ignored
 - Comments are removed from the prompt unless the comment matches the form `#{n}given` or `#blank`
     - These special forms are the only comments removed from the answer
 - Regions are begun and ended by `## {region name} ##`
     - A maximum of one region may be open at a time
     - Regions must be closed before the end of the source
     - All text in a region is only copied into that region
     - Text will be copied into a new file with the regions name in the
       question directory, excluding these special regions:
         explicit: `test` `setup_code`
         implicit: `answer_code` `prompt_code` `question_text`
     - Code in `setup_code` will be parsed to extract exposed names unless the --no-parse
       flag is set. Type annotations and function docstrings are used to fill out server.py
     - Any custom region that clashes with an automatically generated file name
       will overwrite the automatically generated code
 - Import regions allow for the contents of arbitrary files to be loaded as regions
     - They are formatted as `## import {rel_file_path} as {region name} ##`
        where `rel_file_path` is the relative path to the file from the source file
     - Like regular regions, they cannot be used inside of another region"""
