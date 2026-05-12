from __future__ import annotations

from abc import ABC
from collections import defaultdict
from json import dumps
from unittest import TestCase

from lib.consts import DEFAULT_BLANK_PATTERN
from lib.tokens import Tokens, lex


def flatten_into_region_map(tokens: Tokens) -> dict[str, str]:
    col = defaultdict(list)
    for t in tokens.data:
        col[t.region].append(t.text)
    return {k: "".join(v) for k, v in col.items()}


def make_region(name: str, body: str) -> str:
    return f"## {name} ##\n{body}\n## {name} ##"


def make_import(path: str, name: str) -> str:
    return f"## import {path} as {name} ##"


def make_metadata_region(**metadata):
    return make_region("metadata", dumps(metadata))


def lines(*lines):
    return "\n".join(lines)


def n_lines(n: int, body: str):
    return "\n".join(n * [body])


def scrub_blank(txt: str):
    return txt.replace("?", "")


def sub_blank(txt: str):
    return DEFAULT_BLANK_PATTERN.sub(lambda m: f"__[{m.group(1)}]__", txt)


class TestLexABC(TestCase, ABC):
    def assertLexesTo(self, src: str, *, no_region="", **output):
        lexed = lex(src)
        rmap = flatten_into_region_map(lexed)
        output.setdefault("", no_region)
        self.assertDictEqual(output, rmap, msg=f"\n\nSource:\n{src}")

    def assertMetadataIs(self, src: str, **output):
        lexed = lex(src)
        self.assertDictEqual(output, lexed.metadata, msg=f"\n\nSource:\n{src}")

    def assertNoRegions(self, src: str):
        self.assertLexesTo(src, no_region=src)

    def assertSyntaxError(self, src: str):
        with self.assertRaises(SyntaxError):
            _ = lex(src)
