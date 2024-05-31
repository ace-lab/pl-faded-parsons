from abc import ABC, abstractmethod
from typing import Dict, Union
from subprocess import run, PIPE
from os import makedirs, path, popen
from shutil import copytree
from json import (
    loads as json_loads, 
    dumps as json_dumps
)
from yaml import (
    load as yaml_load,
    Loader as Yaml_Loader,
    YAMLError,
)

from lib.name_visitor import AnnotatedName, generate_server, SERVER_DEFAULT
from lib.consts import TEST_DEFAULT, GenerationError
from lib.io_helpers import write_to, Bcolors
from lib.generate_test import make_test_file

DEFAULT_GEMFILE = """source 'https://www.rubygems.org'

gem 'rspec'
gem 'json'
"""
RUBY_SETUP_CMD = """rvm use 2.6.10 && bundle package"""

class AutograderConfig(ABC):

    @abstractmethod
    def info_json_update(self) -> Dict[str, Union[str, Dict[str, Union[bool, str, int]]]]:
        pass

    @abstractmethod
    def populate_tests_dir(self, test_dir: str, answer_code: str, setup_code: str, test_region: str,
                    source_dir: str, pre_code: str = '', post_code: str = '', log_details: bool = True) -> None:
        pass

    def clean_tests_dir(self, test_dir: str) -> None:
        return 

    def generate_server(self, setup_code: str, answer_code: str, *,
                    no_ast: bool = False, tab: str = '    ') -> tuple[str, list[AnnotatedName], list[AnnotatedName]]:
        return (SERVER_DEFAULT, [], [])


autograders: Dict[str, AutograderConfig] = {}

def register_autograder(extension: str = ''):
    with_dot = ('' if extension[0] == '.' else '.') + extension
    without_dot = extension[1:] if extension[0] == '.' else extension

    def add_autograder(cls: AutograderConfig) -> AutograderConfig:
        autograders.update({ with_dot : cls,
                             without_dot : cls })
        return cls
    return add_autograder

def new_autograder_from_ext(extension: str) -> AutograderConfig:
    if extension not in autograders:
        if extension in ("fpp", ''):
            Bcolors.warn('Autograder not specified! Add the "autograder" field ' + \
                        'to the metadata of the source file with the extension' + \
                        ' of the autograder to use (e.g. "rb" for ruby)')
        else:
            Bcolors.warn(f"Autograder for extension '{extension}' not found!")
        print("- Defaulting to Python autograder")
    return autograders.get(extension, PythonAutograder)()

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
                    source_dir: str, pre_code: str = '', post_code: str = '', log_details: bool = True) -> None:
        test_region = test_region if test_region != "" else TEST_DEFAULT
        try:
            try:
                json = json_loads(test_region)
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
        write_to(test_dir, 'ans.py', "\n".join([pre_code, answer_code, post_code]))
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
                'image': 'saasbook/pl-fpp-ruby-autograder',
                'entrypoint': '/grader/run.py',
                'timeout': 30
            }
        }

    def populate_tests_dir(self, test_dir: str, answer_code: str, setup_code: str, test_region: str,
                    source_dir: str, pre_code: str = '', post_code: str = '', log_details: bool = True) -> None:
        app_dir = path.join(path.dirname(f"{test_dir}/"), "app")
        spec_dir = path.join(path.dirname(f"{app_dir}/"), "spec")
        makedirs(spec_dir, exist_ok=True)

        if log_details:
            Bcolors.info('  - Generating grader metadata')

        metadata = json_dumps({
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

    def clean_tests_dir(self, test_dir: str, app_dirname: str = "app") -> None:
        app_dir = path.join(path.dirname(f"{test_dir}/"), app_dirname)
        print(f"Installing gems locally in `{app_dir}` with `{RUBY_SETUP_CMD}` ... ", end="")
        with popen(f"cd {app_dir} && " + RUBY_SETUP_CMD) as out:
            out.read()
            # this print is here to join the thread that runs the command and 
            #   prevent the generator from exiting before gems are installed
            print("Done") 

    def generate_server(self, setup_code: str, answer_code: str, *,
                    no_ast: bool = False, tab: str = '    ') -> tuple[str, list[AnnotatedName], list[AnnotatedName]]:
        return super().generate_server(setup_code, answer_code, no_ast=no_ast, tab=tab)

@register_autograder(extension='.rspec')
class RSpecAutograder(RubyAutograder):

    def info_json_update(self) -> Dict[str, str | Dict[str, bool | str | int]]:
        return {
            'gradingMethod': 'External',
            'externalGradingOptions': {
                'enabled': True,
                'image': 'saasbook/pl-rspec-autograder',
                'entrypoint': '/grader/run.py',
                'timeout': 60
            }
        }

    def _apply_mutation(self, app_dir: str, variant_dir: str, filename: str, patch_str: str) -> int:
        """runs `patch` on the filename with patchfile input `mutations` and returns the error code"""
        in_file = path.join(app_dir, filename)
        out_file = path.join(variant_dir, filename)

        command = [
            "patch",
            "--normal",
            "-o", out_file,
            in_file,
        ]

        return_code = run(command, input=f"{patch_str}\n".encode(), stderr=PIPE).returncode
        return return_code

    def populate_tests_dir(self, test_dir: str, answer_code: str, setup_code: str, test_region: str,
                    source_dir: str, pre_code: str = '', post_code: str = '', log_details: bool = True) -> None:
        # 1) put solution in tests/solution/_submission_file
        # 2) put AG metadata in tests/meta.json
        # 3) put application in tests/common/ (e.g. tests/common/file_at_root.rb)
        # 4) put mutations in tests/var_{variant_name}/file_at_root.rb

        test_dir = path.dirname(f"{test_dir}/")

        ## 1) put solution in tests/solution/_submission_file
        # solution_code = "\n".join([pre_code, answer_code, post_code])
        solution_dir = path.join(test_dir, "solution")
        makedirs(solution_dir, exist_ok=True)
        if log_details:
            print(f"  - Copying solution to {solution_dir} ...")
        write_to(solution_dir, "_submission_file", answer_code)

        ## 2) put AG metadata in tests/meta.json
        try:
            testing_data = yaml_load(test_region, Loader=Yaml_Loader)
        except YAMLError as e:
            raise GenerationError(f"Could not parse YAML in `test` region!") from e
        testing_data["pre-text"] = pre_code
        testing_data["post-text"] = post_code
        if log_details:
            print(f"  - Writing autograder metadata to {test_dir}/meta.json ...")
        write_to(test_dir, "meta.json", json_dumps(testing_data))

        ## 3) put application in tests/common/ (e.g. tests/common/file_at_root.rb)
        common_dir = path.join(test_dir, "common/")
        app_dir = path.join(path.dirname(f"{source_dir}/"), setup_code.strip() + "/")
        if not path.isdir(app_dir):
            raise FileNotFoundError(f"System Under Test was not found at {app_dir}! You may need to modify the `setup_code` region")
        if log_details:
            print(f"  - Copying SUT from {app_dir} to {common_dir} ...")
        copytree(app_dir, common_dir, dirs_exist_ok=True)

        ## 4) put mutations in tests/var_{variant_name}/file_at_root.rb
        # each suite has a set of mutations
        for variant, data in testing_data["mutations"].items():
            variant_dir = path.join(test_dir, f"var_{variant}")
            makedirs(variant_dir, exist_ok=True)
            files = data["files"]

            for file, patch_str in files.items():
                file_path = path.join(variant_dir, file)
                file_dir = path.dirname(file_path)
                makedirs(file_dir, exist_ok=True)

                if log_details:
                    print(f"  - Applying mutation to {file} ...")
                err: int = self._apply_mutation(app_dir, variant_dir, file, patch_str)
                if err: # make sure to swap file and mutations args
                    raise ChildProcessError(f"Unexpected error when applying mutation to {file} in variant {variant}: Exited with code {err}")

    def clean_tests_dir(self, test_dir: str) -> None:
        return super().clean_tests_dir(test_dir, app_dirname = "common")
