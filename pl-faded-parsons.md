# `pl-faded-parsons` element

Build a Parsons-style programming question where students reorder code, fix indentation, and fill in blanks. The element compiles the finished solution into plain source code, so it works with standard PrairieLearn autograders.

## Element Attributes

| Attribute | Type | Default | Description |
| --- | --- | --- | --- |
| `answers-name` | string | - | PrairieLearn answer key for this element. Must be unique within the question. |
| `enable-copy-code` | boolean | false | Show a copy-code control in the widget. |
| `file-name` | string | `user_code.py` | File name used when PrairieLearn stores the submitted solution as an attached file. |
| `format` | `"right"`, `"bottom"`, or `"one-tray"` | `"right"` | Layout of the trays. `right` is the standard starter/solution split. `bottom` places the solution tray below the starter tray. `one-tray` puts the code in a single tray and is the only format that supports `pre-text` and `post-text`. |
| `language` | string | - | Language tag used for syntax highlighting and some controller defaults. |
| `log` | boolean | false | Preserve the browser interaction log for instructor review of edit actions during a submission. |
| `max-indent-level` | integer | 5 | Maximum indent level allowed in the solution tray. Must be nonnegative. |
| `max-optional-fades` | integer | unset | Maximum number of optional fades shown in the problem. The element always shows all required fades, then shows up to this many optional fades. |
| `solution-path` | string | `./solution` | Path to the reference solution that `parse()` can use to populate `correct_answers`. Relative to the question directory. If the file is missing but the answer is fully inferable from optional-only markup, `parse()` can still populate `correct_answers` from the markup. |

### Details

The `format` attribute controls the tray layout:

- `right` is the default Parsons layout with starter and solution trays side by side.
- `bottom` keeps the same behavior but stacks the solution tray below the starter tray.
- `one-tray` combines the code into a single tray and is useful when you want surrounding context around the editable lines.

When using `one-tray` format, you can wrap the editable code with child elements:

- `<pre-text>` for text that appears before the code block
- `<code-lines>` for the code markup block itself
- `<post-text>` for text that appears after the code block

The `<code-lines>` element may also include `visual-indent` to offset the rendered tray visually. That attribute is only supported in `one-tray` mode and only when pre- or post-text is present.

If `log="true"` is set, the widget stores the interaction log in `data["raw_submitted_answers"]["<answers-name>.log"]`. This is useful when instructors want to review how a student built their answer step by step.

## Inner Markup

The element authoring model is built around simple markers inside the question markup. The syntax is listed below:

- `#pin`, `#pin(X)`, ... -- locks a line into the solution tray and sets its starting indent level X (0 if not given).
- `#distractor` marks a line that is **not** part of the solution.
- In C-like authoring contexts, the same markers may also be written with `//` instead of `#`, for example `//pin` and `//distractor`.
- `___` marks a blank that the student must fill in.
- `__(placeholder text)__` marks a blank and sets the default text shown in that blank when the problem is loaded.
- `__[solution_text]__` marks an optional fade. For each variant, the fade is either rendered as a standard blank or omitted entirely and shown as plain code text `solution_text`, which can't be empty.
- `__[solution_text](placeholder text)__` marks an optional fade with a placeholder. When the fade is shown as a blank, the placeholder text is used as the blank's default hint. When the fade is omitted, the visible code is just `solution_text`. The ordering of the solution and placeholder text can be reversed.
- If `max-optional-fades` is set, the problem will show at most that many optional fades. Required fades always show, and optional fades are selected randomly from the optional markup tokens that fit within the cap.

### Example

This example pins the basics of the early return pattern in place (the def, the base-case if, the base-case return, and the recursive return). It adds a few blanks to make solving less mechanical, and inculdes a hint to the student via placeholder text on the base-case return blank. As a final challenge, it includes a red-herring "distractor" line that student *should not* include in their final submission.

```html title="question.html"
<pl-faded-parsons answers-name="fpp" language="python">
  def fibonacci(n: int): #pin
    if n <= 2: #pin(1)
      return __(base case value)__ #pin(2)
    n_less_2 = fibonacci(n - 2)
    n_less_1 = fibonacci(n - 1)
    n_less_0 = fibonacci(n) #distractor
    return n_less_1 + ___ #pin(1)
</pl-faded-parsons>
```

Optional fades can be used for authoring variants. Simply provide more optional fades than the number you set for `max-optional-fades`, and the system will pseudo-randomly pick fades for each variant.

```html title="question.html"
<pl-faded-parsons answers-name="fpp" language="python" max-optional-fades="1">
  def average(a, b):
    return (___ + __[b]__) / __[count]__
</pl-faded-parsons>
```

In one variant, the line renders as `return ([blank] + b) / [blank]`. In another, it renders as `return ([blank] + [blank]) / count`. Note that the first blank (where `a` presumably goes) is a basic, required fade. It does not count towards the optional fade maximum and will always be faded.

### Grading

The submitted answer is compiled into plain source code and stored in `data["submitted_answers"][<answers-name>]`, which means the element can be graded with ordinary code autograders.
The repository contains minimal examples of use with python and ruby.
We suggest using the examples as starting templates for your questions.

Raw submitted answers are encoded in `data["raw_submitted_answers"]["<answers-name>.main"]` in JSON form of the last submission. **We do not recommend accessing this data directly.**
