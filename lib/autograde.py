from abc import ABC, abstractmethod
from typing import Dict, Union
from json import loads, dumps
from os import makedirs, path

from lib.name_visitor import AnnotatedName, generate_server, SERVER_DEFAULT
from lib.consts import TEST_DEFAULT
from lib.io_helpers import write_to, Bcolors
from lib.generate_test import make_test_file

DEFAULT_GEMFILE = """source 'https://www.rubygems.org'

gem 'rspec'
gem 'json'
"""

class AutograderConfig(ABC):

    @abstractmethod
    def info_json_update(self) -> Dict[str, Union[str, Dict[str, Union[bool, str, int]]]]:
        pass

    @abstractmethod
    def populate_tests_dir(self, test_dir: str, answer_code: str, setup_code: str, test_region: str, pre_code: str='', post_code: str='', log_details: bool= True) -> None:
        pass

    def generate_server(self, setup_code: str, answer_code: str, *,
                    no_ast: bool = False, tab: str = '    ') -> tuple[str, list[AnnotatedName], list[AnnotatedName]]:
        return (SERVER_DEFAULT, [], [])


autograders: Dict[str, AutograderConfig] = {}

def register_autograder(extension: str = ''):
    def add_autograder(cls: AutograderConfig) -> AutograderConfig:
        autograders.update({ extension : cls })
        return cls
    return add_autograder

@register_autograder(extension='.py')
class PythonAutograder(AutograderConfig):

    def info_json_update(self) -> Dict[str, Union[str, Dict[str, Union[bool, str, int]]]]:
        return {
            'gradingMethod': 'External',
            'externalGradingOptions': {
                'enabled': True,
                'image': 'prairielearn/grader-python',
                'entrypoint': '/python_autograder/run.sh',
                'timeout': 5
            }
        }

    def populate_tests_dir(self, test_dir: str, answer_code: str, setup_code: str, test_region: str,
                    pre_code: str='', post_code: str='', log_details: bool= True) -> None:
        test_region = test_region if test_region != "" else TEST_DEFAULT
        try:
            try:
                json = loads(test_region)
                success, test_file = True, make_test_file(json)
            except Exception as e:
                success, test_file = False, test_region

            if success and log_details:
                Bcolors.info('  - Generating tests/test.py from json test region')
                write_to(test_dir, 'test_source.json', test_region)
        except SyntaxError as e:
            if log_details:
                Bcolors.fail('    * Generating tests from json failed with error:', e.msg)
                Bcolors.warn('    - Recovering by using test region as python file')
            test_file = test_region

        write_to(test_dir, 'test.py', test_file)
        write_to(test_dir, 'ans.py', answer_code)
        write_to(test_dir, 'setup_code.py', setup_code)

    def generate_server(self, setup_code: str, answer_code: str, *,
                    no_ast: bool = False, tab: str = '    ') -> tuple[str, list[AnnotatedName], list[AnnotatedName]]:
        return generate_server(setup_code, answer_code, no_ast=no_ast, tab=tab)


@register_autograder(extension='.rb')
class RubyAutograder(AutograderConfig):

    def info_json_update(self) -> Dict[str, Union[str, Dict[str, Union[bool, str, int]]]]:
        return {
            'gradingMethod': 'External',
            'externalGradingOptions': {
                'enabled': True,
                'image': 'nalsoon/ruby-autograder',
                'entrypoint': '/grader/run.py',
                'timeout': 30
            }
        }

    def populate_tests_dir(self, test_dir: str, answer_code: str, setup_code: str, test_region: str,
                    pre_code: str='', post_code: str='', log_details: bool= True) -> None:
        app_dir = path.join(path.dirname(f"{test_dir}/"), "app")
        spec_dir = path.join(path.dirname(f"{app_dir}/"), "spec")
        makedirs(spec_dir, exist_ok=True)

        if log_details:
            Bcolors.info('  - Generating grader metadata')

        metadata = dumps({
            "submission_file": "script.rb",
            "submission_root": "",
            "submit_to_line" : -1,
            "pre-text": f"{pre_code}\n", 
            "post-text": f"{post_code}\n",
            "grading_exclusions" : [
            ]
        })

        write_to(spec_dir, 'script_spec.rb', "require_relative '../script.rb'\n\n" + test_region)
        write_to(app_dir, 'script.rb', setup_code)
        write_to(app_dir, 'Gemfile', DEFAULT_GEMFILE)
        write_to(test_dir, 'meta.json', metadata)
        write_to(test_dir, 'solution', answer_code)

    def generate_server(self, setup_code: str, answer_code: str, *,
                    no_ast: bool = False, tab: str = '    ') -> tuple[str, list[AnnotatedName], list[AnnotatedName]]:
        return super().generate_server(setup_code, answer_code, no_ast=no_ast, tab=tab)
