from __future__ import annotations

from .common import (
    lines,
    make_metadata_region,
    make_region,
    scrub_blank,
    sub_blank,
)
from lib.parse import parse_fpp_regions
from lib.tokens import lex
from unittest import TestCase


class TestParseFPP(TestCase):
    def assertParsesTo(self, src: str, *, answer_code="", prompt_code="", metadata=None, **output):
        lexed = lex(src)
        parsed = parse_fpp_regions(lexed)
        output.setdefault("metadata", metadata or {})
        output.setdefault("answer_code", answer_code)
        output.setdefault("prompt_code", prompt_code)
        self.assertDictEqual(output, parsed, msg=f"\n\nSource:\n{src}")

    def assertSyntaxError(self, src: str):
        lexed = lex(src)
        with self.assertRaises(SyntaxError):
            _ = parse_fpp_regions(lexed)

    def test_empty_src(self):
        """ Empty source results in {} metadata and blank answer_code and prompt_code """
        self.assertParsesTo("")

    def test_no_comments_in_strings(self):
        """ Comments are not captured in str literals """
        for c in ["'", '"', "`", '"""', "'''"]:
            with self.subTest(f"no comments within {c}s"):
                txt = 's = " line# 7 "'
                self.assertParsesTo(txt, answer_code=txt, prompt_code=txt)

    def test_docstring_question_text(self):
        """ Leading docstrings are appended to the question_text region """
        q_html = "<question> text </question>"
        ans = "answer = 3"
        self.assertParsesTo(
            lines(f"'''{q_html}'''", "", ans),
            answer_code=ans,
            prompt_code=ans,
            question_text=q_html,
        )
        t = "<i>hello</i>"
        r = make_region("question_text", t)
        self.assertParsesTo(
            lines(f"'''{q_html}'''", "", ans, r),
            answer_code=ans,
            prompt_code=ans,
            question_text=lines(q_html, t),
        )
        self.assertParsesTo(
            lines(r, f"'''{q_html}'''", "", ans, r),
            answer_code=ans,
            prompt_code=ans,
            question_text=lines(t, q_html, t),
        )

    def test_regular_comment_splitting(self):
        """ Regular comments should only appear in prompt_code not answer_code """
        txt = lines("# c0", "a = 4  # c1", "a += 2", "\t\t# c1", "")
        self.assertParsesTo(txt, answer_code=txt.strip(), prompt_code=lines("a = 4", "a += 2"))

    def test_blank_parsing(self):
        """ Blanks appear between ?'s by default, are substituted with lib.consts.BLANK_DEFAULT
            in the answer_code. The question marks are removed from the answer code.
        """
        txt = lines("for ?i? in range(?1, 10?):", "\t?a? += i", "?return a?")
        self.assertParsesTo(txt, answer_code=scrub_blank(txt), prompt_code=sub_blank(txt))

        txt = lines("for _ in range?(1, 10):", '\ta? += "?"', "return a.is_odd? # fun?")
        self.assertParsesTo(
            txt,
            answer_code=txt,
            prompt_code=lines("for _ in range?(1, 10):", '\ta? += "?"', "return a.is_odd?"),
        )

    def test_pin_special_comment(self):
        """ Special comments appear in the prompt_code, but not the answer_code.
            The special comment that indicates a line as pinned in the prompt is
            /#pin or #pin(<indentation level>)/
        """
        txt = lines("def foo(x): #pin", "\tx *= x", "\treturn x #pin(1)", "")
        self.assertParsesTo(
            txt,
            answer_code=lines("def foo(x):", "\tx *= x", "\treturn x"),
            prompt_code=txt.strip(),
        )

        txt = lines("def foo(x): #pin(10000)", "\tx *= x", "\treturn x #pin(000)", "")
        self.assertParsesTo(
            txt,
            answer_code=lines("def foo(x):", "\tx *= x", "\treturn x"),
            prompt_code=txt.strip(),
        )

        with self.subTest("poorly formatted special comments become regular comments"):
            txt = lines("def foo(x): #pinning", "\tx *= x", "\treturn x #pinned", "")
            self.assertParsesTo(
                txt,
                answer_code=txt.strip(),
                prompt_code=lines("def foo(x):", "\tx *= x", "\treturn x"),
            )

    def test_blank_default_special_comment(self):
        """ Special comments appear in the prompt_code, but not the answer_code.
            The special comment that indicates placeholder text for a fade is
            /#blank <blank placeholder text>/
        """
        txt = lines("x, y = a[?3:-3?]  #blank _:_")
        self.assertParsesTo(txt, answer_code="x, y = a[3:-3]", prompt_code=sub_blank(txt))
        txt = lines("x, y = a[?3:-3?]  #blank")
        self.assertParsesTo(txt, answer_code="x, y = a[3:-3]", prompt_code=sub_blank(txt))

        with self.subTest("poorly formatted special comments become regular comments"):
            txt = lines("x, y = a[?3:-3?]  #blahblah _:_")
            self.assertParsesTo(
                txt,
                answer_code=scrub_blank(txt),
                prompt_code=sub_blank("x, y = a[?3:-3?]"),
            )

    def test_many_comments(self):
        """ Interspersing special and regular comments does not effect behavior """
        txt = lines(
            "def func(x: ?str?): #pin #blank _type_",
            "\tx.modify(42) # 42 is always magic ",
            "\treturn ?x.finish()? #pin(1) #blank x._ # huzzah!",
        )
        self.assertParsesTo(
            txt,
            answer_code=scrub_blank(
                lines(
                    "def func(x: ?str?):",
                    "\tx.modify(42) # 42 is always magic",
                    "\treturn ?x.finish()? # huzzah!",
                )
            ),
            prompt_code=sub_blank(
                lines(
                    "def func(x: ?str?): #pin #blank _type_",
                    "\tx.modify(42)",
                    "\treturn ?x.finish()? #pin(1) #blank x._",
                )
            ),
        )

    def test_custom_fading(self):
        """ Blank delimiters can be set through a field 'blankDelimiter' in the metadata
            by one of three values:
                - a str that is the stop & start delimiter
                - an `{ 'start': str, 'stop': str }` object
                - an `{ 'pattern': regex_str }` object

            Delimiters may be special characters in regex, but are not treated as regex
            unless the 'pattern' tag is specified. (e.g. 'blankDelimiter': '$' means
            that $x$ is a valid fade.)
        """
        metadata = {"blankDelimiter": "--"}
        self.assertParsesTo(
            lines(
                make_metadata_region(**metadata),
                "",
                "4.--times-- do #blank _verb_",
                "\tputs --i.?dis?belief??--",
                "end",
                "",
            ),
            metadata=metadata,
            answer_code=lines("4.times do", "\tputs i.?dis?belief??", "end"),
            prompt_code=lines(
                "4.__[times]__ do #blank _verb_",
                "\tputs __[i.?dis?belief??]__",
                "end",
            ),
        )

        with self.subTest("works with regex reserved chars"):
            metadata = {"blankDelimiter": "$"}
            self.assertParsesTo(
                lines(
                    make_metadata_region(**metadata),
                    "",
                    "4.$times$ do #blank _verb_",
                    "\tputs $i.?dis?belief??$",
                    "end",
                    "",
                ),
                metadata=metadata,
                answer_code=lines("4.times do", "\tputs i.?dis?belief??", "end"),
                prompt_code=lines(
                    "4.__[times]__ do #blank _verb_",
                    "\tputs __[i.?dis?belief??]__",
                    "end",
                ),
            )

            metadata = {"blankDelimiter": {"start": "^", "end": "$"}}
            self.assertParsesTo(
                lines(
                    make_metadata_region(**metadata),
                    "",
                    "4.^times$ do #blank _verb_",
                    "\tputs ^i.?dis?belief??$",
                    "end",
                    "",
                ),
                metadata=metadata,
                answer_code=lines("4.times do", "\tputs i.?dis?belief??", "end"),
                prompt_code=lines(
                    "4.__[times]__ do #blank _verb_",
                    "\tputs __[i.?dis?belief??]__",
                    "end",
                ),
            )

        with self.subTest("custom regex pattern"):
            metadata = {"blankDelimiter": {"pattern": r"--(.+?)%-%"}}
            self.assertParsesTo(
                lines(
                    make_metadata_region(**metadata),
                    "",
                    "4.--times%-% do #blank _verb_",
                    "\tputs --i.?dis?belief??%-%",
                    "end",
                    "",
                ),
                metadata=metadata,
                answer_code=lines("4.times do", "\tputs i.?dis?belief??", "end"),
                prompt_code=lines(
                    "4.__[times]__ do #blank _verb_",
                    "\tputs __[i.?dis?belief??]__",
                    "end",
                ),
            )

    def test_illegal_custom_fading(self):
        """ Custom fading cannot use a builtin delimiter (` ' " #), must
            capture exactly one substring when it matches, and must not
            match on the empty string
        """

        def assertBadCustomDelim(*args, **kwargs):
            delim = args[0] if args else kwargs
            metadata = make_metadata_region(blankDelimiter=delim)
            self.assertSyntaxError(metadata)

        for c in '#`\'"':
            with self.subTest(f"cannot shadow builtin delimiter {c}"):
                assertBadCustomDelim(c)
                assertBadCustomDelim(start="-", end=c)
                assertBadCustomDelim(start=c, end="-")
                assertBadCustomDelim(pattern=c + r"(.+?)-")
                assertBadCustomDelim(pattern=r"-(.+?)" + c)

        with self.subTest("custom groups must capture exactly one substring"):
            assertBadCustomDelim(pattern=r"-.*?-")
            assertBadCustomDelim(pattern=r"-(.*?):(.*?)-")

        with self.subTest("blankDelimiter must not match empty string"):
            assertBadCustomDelim(pattern=".*")

        with self.subTest("blankDelimiter must adhere to schema"):
            assertBadCustomDelim(0)
            assertBadCustomDelim("")
            assertBadCustomDelim([])
            assertBadCustomDelim(badSchema="-")

    def test_standard_input(self):
        """ Generates a standard input (polynomial_evaluation.py) and tests the output """
        q_lines = (
            "Write a function <code>poly</code> that calculates the values of a  ",
            "polynomial with the given coefficients at the given value of <code>x</code>,",
            "\tie, evaluate $$f(x) = \sum_i \textrm{coeffs}_i ~ x^i$$\t",
        )
        q_text = "\n".join(q_lines)
        q_trim = "\n".join(map(str.rstrip, q_lines))

        setup = lines("a: int = 3", "b = a + 4", "l: list[int] = [1, 2, 3]", "c = l[0] = 3")

        raw = lines(
            "def poly(coeffs, x): #pin",
            "    # Keep track of the total as we iterate through each term.",
            "    # Each term is of the form coeff*(x**power).",
            "    total = ?0? #blank test #pin(1) # total starts at 0",
            "    ",
            "    # Extract the power and coefficient for each term.",
            "    for ?power, coeff? in enumerate(coeffs):",
            "        # Add the value of the term to the total.",
            "        ?total? = total + coeff * (x ** power) #pin(2)",
            "    return total #pin(1)",
        )

        ans = lines(
            "def poly(coeffs, x):",
            "    # Keep track of the total as we iterate through each term.",
            "    # Each term is of the form coeff*(x**power).",
            "    total = 0 # total starts at 0",
            "",
            "    # Extract the power and coefficient for each term.",
            "    for power, coeff in enumerate(coeffs):",
            "        # Add the value of the term to the total.",
            "        total = total + coeff * (x ** power)",
            "    return total",
        )
        ppt = lines(
            "def poly(coeffs, x): #pin",
            "    total = __[0]__ #blank test #pin(1)",
            "    for __[power, coeff]__ in enumerate(coeffs):",
            "        __[total]__ = total + coeff * (x ** power) #pin(2)",
            "    return total #pin(1)",
        )

        test = lines(
            "from pl_helpers import name, points",
            "from pl_unit_test import PLTestCase",
            "from code_feedback import Feedback",
            "",
            "class Test(PLTestCase):",
            "    @points(1)",
            '    @name("testing single case")',
            "    def test_0(self):",
            "        case = [[10], 3]",
            "        points = 0",
            "        user_val = Feedback.call_user(self.st.poly, *case)",
            "        ref_val = self.ref.poly(*case)",
            "        if Feedback.check_scalar(f\"args: {case}\", ref_val, user_val):",
            "            points += 1",
            "        Feedback.set_score(points)",
            "",
        )

        src = lines(
            f'"""{q_text}"""',
            "",
            make_region("setup_code", setup),
            "",
            raw,
            "",
            "",
            make_region("test", test),
            "",
        )

        self.assertParsesTo(
            src,
            answer_code=ans,
            prompt_code=ppt,
            test=test.strip(),
            setup_code=setup,
            question_text=q_trim,
        )
