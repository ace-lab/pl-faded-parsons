from abc import ABC, abstractmethod
import os
import chevron

from dataclasses import dataclass, field, replace
from typing import Optional, Type, Union



JsonValue = Union[float, int, bool, str, list['JsonValue'], dict[str, 'JsonValue']]
JsonType = Union[bool, Type[str], Type[bool], type['NoEscapeStr'], dict[str, Union['Maybe', 'JsonType']], 'Many']


# replace with Optional
@dataclass(frozen=True)
class Maybe:
    inner: JsonType

# replace with list
@dataclass(frozen=True)
class Many:
    inner: JsonType

class NoEscapeStr(str): pass


@dataclass(slots=True, frozen=True)
class Symbol(ABC):
    parent: Optional['Scope']

    @abstractmethod
    def reify(self) -> JsonType:
        pass

    def update(self, **kwargs): return replace(self, **kwargs)


@dataclass(slots=True, frozen=True)
class Variable(Symbol):
    no_escape: bool = False

    def reify(self) -> JsonType:
        return NoEscapeStr if self.no_escape else str


@dataclass(slots=True, frozen=True)
class Scope(Symbol):
    fields: dict[str, 'Symbol'] = field(default_factory=dict)
    partials: dict[str, 'Scope'] = field(default_factory=dict)

    def reify(self) -> JsonType:
        fields_type = {k: v.reify() for k, v in self.fields.items()}
        for v in self.partials.values():
            fields_type.update(v.reify())
        return fields_type


@dataclass(slots=True, frozen=True)
class Section(Scope):
    section: bool = False
    inverse: bool = False

    def __post_init__(self): assert self.section or self.inverse

    def reify(self) -> JsonType:
        fields_type = Scope.reify(self)
        has_fields = bool(fields_type)
        fields_type = Many(fields_type)
        match self.section, self.inverse:
            case True, True:
                return Maybe(fields_type) if has_fields else bool
            case True, False:
                return fields_type if has_fields else Maybe(True)
            case False, True if not has_fields:
                return Maybe(False)
            case _, _:
                raise ValueError('incoherent non-section section!', self)



def read_mustache_params_type(template: str, working_dir) -> Scope:
    top = current = Scope(parent=None)

    def update_section_field(name, **kwargs) -> Section:
        if name not in current.fields:
            current.fields[name] = Section(current, **kwargs)
        else:
            assert isinstance(current.fields[name], Section)
            current.fields[name] = current.fields[name].update(**kwargs)
        return current.fields[name]

    for kind, value in chevron.tokenizer.tokenize(template):
        match kind:
            case 'literal': pass
            case 'variable':
                current.fields[value] = Variable(current)
            case 'no escape':
                current.fields[value] = Variable(current, no_escape=True)
            case 'section':
                current = update_section_field(value, section=True)
            case 'inverted section':
                current = update_section_field(value, inverted=True)
            case 'end':
                assert current.parent, f'section "{value}" ended before it began'
                current = current.parent
            case 'partial':
                with open(os.path.join(working_dir, value + '.mustache'), 'r') as f:
                    t = f.read()
                # potential recursive loop!!
                current.partials[value] = read_mustache_params_type(t, working_dir)
            case x:
                raise ValueError(x)

    return top


def json_type_to_json_schema(t: JsonType, allow_implicit_falsy=False) -> JsonValue:
    if type(t) is Maybe:
        raise ValueError('cannot generate schema for maybe type')
    if type(t) is Many:
        return { "type": "array", "items": json_type_to_json_schema(t.inner, allow_implicit_falsy) }
    if type(t) is bool:
        return { "enum": [t] }
    if t is bool:
        return { "type": "boolean" }
    if t is str:
        return { "type": "string" }
    if t is NoEscapeStr:
        return { "type": "string", "$commment": "no escaping!"}
    if type(t) is dict:
        return {
            "type": "object",
            "properties": {
                k: json_type_to_json_schema(v if type(v) is not Maybe else v.inner, allow_implicit_falsy) \
                    for k, v in t.items()
            },
            "required": [k for k, v in t.items() if not allow_implicit_falsy and type(v) is not Maybe]
        }
    raise ValueError(f'{t}')

def print_typish(t: JsonType, space_per_indent=2):
    indent=0

    def write(text: str):
        leader = '\n' + indent * space_per_indent * ' '
        print(leader.join(text.split('\n')), end='')

    def pprint(t):
        nonlocal indent
        if type(t) is Maybe: raise ValueError(t)

        if type(t) is dict:
            write('{')
            indent += 1
            for k, v in t.items():
                write('\n')
                write(k)
                if type(v) is Maybe:
                    write('?')
                    v = v.inner
                write(': ')
                pprint(v)
                write(',')
            indent -= 1
            write('\n}')
        elif type(t) is Many:
            pprint(t.inner)
            write('[]')
        elif type(t) is bool:
            write('true' if t else 'false')
        elif t is str:
            write('string')
        elif t is bool:
            write('boolean')
        elif t is NoEscapeStr:
            write('NoEscape<str>')
        else:
            raise ValueError(f'{t}')

    if type(t) is Maybe: t = t.inner
    if type(t) is Many: t = t.inner
    pprint(t)
    print()


def __main__():
    import glob
    import json


    working_dir = '/Users/logan_caraco/Documents/GitHub/pl-ucb-cs169/elements/pl-faded-parsons/'
    for path in glob.glob(working_dir + '/*.mustache'):
        print(path)
        with open(path, 'r') as f:
            template = f.read()

        scope = read_mustache_params_type(template, working_dir)
        print(scope)
        jtype = scope.reify()
        print_typish(jtype)

        print(json.dumps(json_type_to_json_schema(jtype, allow_implicit_falsy=True), indent=2))


if __name__ == '__main__':
    __main__()
