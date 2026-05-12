from __future__ import annotations

from collections import defaultdict
from itertools import cycle
from json import JSONDecoder
from pathlib import Path
from unittest.mock import patch

from .common import (
    TestLexABC,
    lines,
    make_import,
    make_region,
    n_lines,
)
from lib.tokens import lex


SAMPLE_TEXTS = [
    "alpha beta gamma delta epsilon zeta eta theta iota kappa lambda mu",
    "one two three four five six seven eight nine ten eleven twelve",
    "red orange yellow green blue indigo violet black white gray silver gold",
    "apple banana cherry date elderberry fig grape huckleberry kiwi lemon mango",
    "north south east west up down left right forward backward inward outward",
    "cat dog mouse bird fish lizard frog horse sheep goat pig cow",
    "spring summer autumn winter rain snow wind sun cloud storm fog",
    "paper pencil eraser notebook ruler compass marker chalk paint ink",
    "lorem ipsum dolor sit amet consectetur adipiscing elit sed do eiusmod",
    "alpha one bravo two charlie three delta four echo five foxtrot six",
    "mercury venus earth mars jupiter saturn uranus neptune pluto ceres eris",
    "first second third fourth fifth sixth seventh eighth ninth tenth eleventh",
]


class TestLex(TestLexABC):
    def test_empty_src(self):
        """ An empty source should return `{ '': '' }` """
        self.assertLexesTo("")

    def test_simple_region_delims(self):
        """ Single char names and ws only contents """
        txt = "## r ##\n## r ##"
        self.assertLexesTo(txt, r="")
        txt += "\n"
        self.assertLexesTo(txt, r="")
        txt += "\n"
        self.assertLexesTo(txt, no_region="\n", r="")

        txt = "## r ##\n\n## r ##"
        self.assertLexesTo(txt, r="")
        txt = "## r ##\n\n\n## r ##"
        self.assertLexesTo(txt, r="\n")

    def test_dirty_region_delims(self):
        """ Whitespace before and text after region delim tags is ignored """
        txt = """
           \t ## dirty ## hi there! ##
        all good
        ## dirty #### random text $$%$%"""
        self.assertLexesTo(txt, dirty="        all good")

    def test_unbalanced_region_delims(self):
        """ Checks unbalanced delims throw SyntaxErrors """
        with self.subTest("unbalanced w/valid start"):
            txt = "## not_okay ##\n"
            self.assertSyntaxError(txt)
            txt = "outer text\n\n## not_okay ##\n\ninner text...\n"
            self.assertSyntaxError(txt)
            txt = "\t\t## region ### hi"
            self.assertSyntaxError(txt)

        with self.subTest("integration"):
            txt = f"a \n{make_region('r0', 'hi there')} \nb \n## bad ##\n inner"
            self.assertSyntaxError(txt)

    def test_start_region_without_closing_previous(self):
        """ Region delimiters appearing in regions throw SyntaxErrors """
        txt = make_region("okay", "text\n " + make_region("not okay", "bad") + "\n more text")
        self.assertSyntaxError(txt)
        txt = f"a \n{make_region('r0', 'hi there')} \n{make_region('r1', '## bad ##')}"
        self.assertSyntaxError(txt)

    def test_import_region_without_closing_previous(self):
        """ Import regions appearing in regions throw SyntaxErrors """
        i_r = make_import("file.txt", "bad")
        txt = make_region("okay", f"text\n{i_r}\n more text")
        self.assertSyntaxError(txt)
        txt = f"a \n{make_region('r0', 'hi there')} \n{make_region('r1', i_r)}"
        self.assertSyntaxError(txt)

    def test_almost_region_delim_false_positives(self):
        """ Test things that almost qualify as region delims """
        with self.subTest("regions must be named"):
            self.assertNoRegions("####")
            self.assertNoRegions("#####")

        with self.subTest("regions must be named non whitespace"):
            self.assertNoRegions("## ##")
            self.assertNoRegions("## \t ##")
            self.assertNoRegions("## \t   ##")

        with self.subTest("regions begin with exactly ## and end with at least ##"):
            self.assertNoRegions("### region ##")
            self.assertNoRegions("# region ##")
            self.assertNoRegions("### region ###")
            self.assertNoRegions("#### region ####")

    def test_region_concat(self):
        """ Regions with the same name should concatenate in the order they appear """
        rbody = "body 0\nbody1\nbody2\n\n"
        r = make_region("r", rbody) + "\n"
        self.assertLexesTo(3 * r, r=n_lines(3, rbody))
        sbody = "body a\nbodyb\nbodyc\n\n"
        s = make_region("s", sbody) + "\n"
        self.assertLexesTo(r + s + r + s + r, s=n_lines(2, sbody), r=n_lines(3, rbody))

        txt = "\n".join((make_region("r", "1"), make_region("r", "2"), make_region("r", "3")))
        self.assertLexesTo(txt, r=lines("1", "2", "3"))

    def test_empty_metadata(self):
        """ Empty input or metadata regions should both yield {} metadata """
        self.assertMetadataIs("")
        self.assertMetadataIs(make_region("metadata", ""))

    def test_falsy_metadata(self):
        """ Falsy objects in metadata is interpreted as {} """
        self.assertMetadataIs("")
        self.assertMetadataIs(make_region("metadata", "0"))
        self.assertMetadataIs(make_region("metadata", "[]"))
        self.assertMetadataIs(make_region("metadata", "{}"))
        self.assertMetadataIs(make_region("metadata", '""'))
        self.assertMetadataIs(make_region("metadata", "null"))
        txt = make_region("metadata", "") + "\n" + make_region("metadata", "{}") + "\n" + make_region("metadata", "")
        self.assertMetadataIs(txt)

    def test_import_concat(self):
        """ Check that import regions concat to themselves like regular regions """
        file_data = "imported file:\n3\n2\n1"
        with patch.object(Path, "exists", lambda self: str(self) == "file.txt"), patch.object(
            Path, "read_text", lambda self, *args, **kwargs: file_data
        ):
            i_r = make_import("file.txt", "imported")
            txt = i_r + "\n" + make_region("r", "data") + ("\n" + i_r) * 2
            self.assertLexesTo(txt, r="data", imported=3 * file_data)

    def test_multiple_imports(self):
        """ Importing multiple sources is possible """
        file_data = "imported file:\n3\n2\n1"
        with patch.object(
            Path,
            "exists",
            lambda self: str(self) in {"f1.txt", "f2.txt"},
        ), patch.object(Path, "read_text", lambda self, *args, **kwargs: file_data):
            txt = make_region("r", "data") + "\n" + make_import("f1.txt", "i1") + "\n" + make_import("f2.txt", "i2")
            self.assertLexesTo(txt, i1=file_data, i2=file_data, r="data")

    def test_valid_import(self):
        """ Valid imports read file contents """
        path = "README.md"
        with open(path) as rdme:
            lines = "".join(rdme.readlines())
        txt = make_import(path, "readme")
        self.assertLexesTo(txt, readme=lines)

    def test_valid_import_content(self):
        """ Valid imports read file contents and do not edit other regions """
        file_data = "imported file:\n3\n2\n1"
        with patch.object(Path, "exists", lambda self: str(self) == "file.txt"), patch.object(
            Path, "read_text", lambda self, *args, **kwargs: file_data
        ):
            i_r = make_import("file.txt", "imported")
            self.assertLexesTo(i_r, imported=file_data)

            txt = make_region("r", "data") + "\n" + i_r
            self.assertLexesTo(txt, imported=file_data, r="data")

    def test_import_bad_path(self):
        """ Bad import paths result in FileNotFoundErrors or OSErrors """
        with self.subTest("absolute dir"):
            path = "~/Documents"
            with self.assertRaises(OSError):
                _ = lex(make_import(path, "imported"))

        with self.subTest("absolute non-existent file"):
            path = "~/badsasdfasdfasdfasdfsadfas.txt"
            with self.assertRaises(FileNotFoundError):
                _ = lex(make_import(path, "imported"))

        with self.subTest("relative dir"):
            path = "./lib"
            with self.assertRaises(OSError):
                _ = lex(make_import(path, "imported"))

        with self.subTest("relative non-existent file"):
            path = "./dont-readme.md"
            with self.assertRaises(FileNotFoundError):
                _ = lex(make_import(path, "imported"))

        with self.subTest("unix-style relative non-existent file"):
            path = "badsasdfasdfasdfasdfsadfas.txt"
            with self.assertRaises(FileNotFoundError):
                _ = lex(make_import(path, "imported"))

    def test_import_json_as_metadata(self):
        """ Reading a metadata json with imports is the same as with decoders """
        with open("./info.json") as f:
            ls = "".join(f.readlines())
        txt = make_import("info.json", "metadata")
        json = JSONDecoder().decode(ls)
        self.assertMetadataIs(txt, **json)


class TestRandomLex(TestLexABC):
    @classmethod
    def setUpClass(cls):
        cls.test_strings = SAMPLE_TEXTS

    def test_no_regions(self):
        """ A random text file with no regions of any kind. """
        self.assertNoRegions(self.test_strings[0])

    def test_empty_regions(self):
        """ A randomly named set of empty regions """
        rnames = self.test_strings[0].split()[:3]
        txt = "\n".join(make_region(name, "") for name in rnames)
        output = {name: "" for name in rnames}
        self.assertLexesTo(txt, **output)

    def test_random_regions(self):
        """ A randomly filled and named set of regions """
        rnames = self.test_strings[0].split()[:3]
        rbodies = self.test_strings[1:4]
        txt = "\n".join(make_region(name, body) for name, body in zip(rnames, rbodies))
        output = defaultdict(str)
        for name, body in zip(rnames, rbodies):
            output[name] += body
        output[""] += ""
        self.assertLexesTo(txt, **output)

    def test_mixed_regions_and_no_region(self):
        """ A randomly filled and named set of regions, interspersed with random text """
        str_iter = iter(self.test_strings)
        rnames = cycle(next(str_iter).split()[:3])
        txt = []
        output = defaultdict(list)
        unmatched = ""
        for name, body, no_r in zip(rnames, str_iter, str_iter):
            txt.append(make_region(name, body))
            output[name].append(body)

            txt.append(no_r)
            unmatched += no_r

        output = {name: lines(*body) for name, body in output.items()}
        output[""] = unmatched
        self.maxDiff = 5000
        self.assertLexesTo(lines(*txt), **output)
