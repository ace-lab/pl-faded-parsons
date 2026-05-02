# `pl-faded-parsons` Data Passing

This document traces the data contracts inside `pl-faded-parsons` across:

- Python controller: `pl-faded-parsons.py`
- Question template: `pl-faded-parsons-question.mustache`
- Code line partial: `pl-faded-parsons-code-line.mustache`
- Browser widget: `pl-faded-parsons.js`
- Submission and answer templates

It is meant to answer two questions:

1. What data shape is expected at each boundary?
2. Which names/fields must stay aligned across `.py`, `.mustache`, and `.js`?

## Canonical Data Flow

There are two main flows:

- Render-time flow: Python -> Mustache -> DOM -> JS config
- Submission-time flow: DOM/JS -> hidden inputs -> PrairieLearn `raw_submitted_answers` -> Python parse -> PrairieLearn `submitted_answers`

The canonical parsed answer is:

```python
data["submitted_answers"][answers_name] = compiled_student_code
```

The hidden raw UI state is:

```python
data["raw_submitted_answers"][f"{answers_name}.main"]
data["raw_submitted_answers"][f"{answers_name}.log"]
```

Interaction logging is optional and disabled by default. Set `log="true"` on the
element to preserve the browser event log in `raw_submitted_answers`.

## Lifecycle

### 1. `prepare()`

File: `pl-faded-parsons.py`

- Validates element attributes.
- Validates `answers-name` uniqueness with `pl.check_answers_names(...)`.
- Reads `log="true|false"` and defaults logging to `false`.

Important contract:

- `answers-name` is the canonical PrairieLearn key for this element.

### 2. `render(panel="question")`

File: `pl-faded-parsons.py`

- Builds a small config dictionary from the element HTML.
- Reconstructs state from `raw_submitted_answers` if `"{answers_name}.main"` exists.
- Otherwise builds trays from element markup.
- Converts the state into the plain dictionary shape expected by Mustache.
- Renders `pl-faded-parsons-question.mustache`.

### 3. Browser initialization

Files:

- `pl-faded-parsons-question.mustache`
- `pl-faded-parsons-code-line.mustache`
- `pl-faded-parsons.js`

The question template creates:

- two hidden inputs
  - `name="{{answers_name}}.main"`
  - `name="{{answers_name}}.log"`
- one or two sortable trays
- floating help/copy controls
- a `ParsonsWidget` config whose selectors must match the rendered DOM

### 4. Browser-side state persistence

File: `pl-faded-parsons.js`

The widget serializes the current UI state into the hidden `.main` input and the event log into the hidden `.log` input.

That means PrairieLearn receives:

- `raw_submitted_answers["<answers-name>.main"]`
- `raw_submitted_answers["<answers-name>.log"]`

### 5. `parse()`

File: `pl-faded-parsons.py`

On parse:

- Python reconstructs the submission from `raw_submitted_answers["<answers-name>.main"]`
- compiles the solution tray into plaintext code
- stores the canonical answer in `submitted_answers[answers_name]`
- adds a submitted file using `file-name` or the default `user_code.py`

## Boundary Map

### Python -> Mustache

File: `pl-faded-parsons.py`

`render(panel="question")` builds a dictionary with:

- `answers_name: str`
  - used for hidden input names in the question template
- `language: str`
  - used for syntax highlighting and copied onto the root widget DOM node
- `previous_log: str`
  - JSON string used to initialize the hidden log input
  - defaults to `[]` unless `log="true"` is set on the element
- `logging_enabled: bool`
  - controls whether the browser widget records interaction logs
- `uuid: str`
  - used to build DOM ids and JS selectors
- `starter`
  - rendered only when a starter tray exists
- `given`
  - always rendered
- `pre_text`
  - optional block before the solution tray
  - only supported when `format="one-tray"` or the legacy alias `format="no-code"`
  - normalized in Python using the first non-empty line as the shared leading whitespace baseline
  - raises `IndentationError` if later lines do not preserve that baseline prefix
  - rendered with `lines` and `indent` fields
- `post_text`
  - optional block after the solution tray
  - only supported when `format="one-tray"` or the legacy alias `format="no-code"`
  - normalized in Python using the last non-empty line as the shared leading whitespace baseline
  - raises `IndentationError` if earlier lines do not preserve that baseline prefix
  - rendered with `lines` and `indent` fields

### Mustache -> DOM

File: `pl-faded-parsons-question.mustache`

Generated DOM state includes:

- root widget element
  - `id="pl-faded-parsons-{{uuid}}"`
  - `language="{{language}}"`
- hidden raw-state inputs
  - `.main`, `name="{{answers_name}}.main"`
  - `.log`, `name="{{answers_name}}.log"`
- tray ids/selectors
  - `#starter-code-{{uuid}}`
  - `#ol-starter-code-{{uuid}}`
  - `#solution-{{uuid}}`
  - `#ol-solution-{{uuid}}`
- floating controls id
  - `#widget-controls-{{uuid}}`

These ids must stay aligned with the config object passed into `new ParsonsWidget(...)`.

### Mustache line schema

Files:

- `pl-faded-parsons.py`
- `pl-faded-parsons-code-line.mustache`

Each rendered code line is built from:

- `indent`
  - rendered as `style="--pl-faded-parsons-indent: {{indent}};"`
  - stored as a logical indent level and converted to visual width by CSS/JS
- `segments`
  - alternates between:
    - `code.content`, `code.language`
    - `blank.default`, `blank.width`

This mirrors one saved line in Python:

```python
{
    "indent": int,
    "codeSnippets": list[str],
    "blankValues": list[str],
}
```

The invariant is:

```text
len(codeSnippets) == len(blankValues) + 1
```

The `code-lines` child may also carry an optional `visual-indent` attribute
that is threaded through the render config as a nonnegative integer. It
defaults to `0` and is intended for later tray-level styling.

### JS config -> DOM selectors

File: `pl-faded-parsons-question.mustache`

`ParsonsWidget` receives:

- `main`
- `uuid`
- `storage`
- optionally `logStorage`
- `loggingEnabled`
- `ariaDescriptor`
- `ariaDetails`
- `toolbar`
- `solution`
- `solutionList`
- `maxIndentLevel`
- `visualIndent`
- optionally `starter`
- optionally `starterList`

`validateConfig()` in `pl-faded-parsons.js` requires:

- `uuid`
- `solution`
- `solutionList`
- `main`
- `toolbar`
- `storage`
- `logStorage` when `loggingEnabled` is true

Starter selectors are optional.

## Raw Submission Schema

### Hidden `.main` input

File: `pl-faded-parsons.js`

`storeStudentProgress()` writes this JSON string:

```json
{
  "starter": [
    {
      "indent": 0,
      "codeSnippets": ["..."],
      "blankValues": ["..."]
    }
  ],
  "solution": [
    {
      "indent": 1,
      "codeSnippets": ["..."],
      "blankValues": ["..."]
    }
  ]
}
```

Important mapping:

- JS `starter` -> Python `state["starter"]`
- JS `solution` -> Python `state["solution"]`

This schema is read in `pl-faded-parsons.py` by validating the JSON and returning:

```python
{
    "starter": [...],
    "solution": [...],
    "log": [...],
}
```

### Hidden `.log` input

File: `pl-faded-parsons.js`

When `loggingEnabled` is true, `addLogEntry()` appends entries shaped like:

```json
{
  "timestamp": "...",
  "tag": "problemOpened",
  "data": {}
}
```

Observed tags include:

- `problemOpened`
- `editBlank`
- `removeOutput`
- `moveInput`
- `moveOutput`
- `addOutput`

This schema is read back into Python as a list of dictionaries with
`timestamp`, `tag`, and `data` keys.

## Python Internal State

### State dictionary

File: `pl-faded-parsons.py`

Python reconstructs the raw submission into:

```python
{
    "solution": [{"indent": ..., "codeSnippets": [...], "blankValues": [...]}, ...],
    "starter": [{"indent": ..., "codeSnippets": [...], "blankValues": [...]}, ...],
    "log": [{"timestamp": "...", "tag": "...", "data": {...}}, ...],
}
```

This internal representation is then used for:

- re-rendering prior student state on the question panel
- generating the compiled code string

### Compiled code

File: `pl-faded-parsons.py`

`parse()` and `render(panel="submission")` compile only the `solution` tray.

Each line is rendered by:

```python
indent * "    " + "".join(interleave(codeSnippets, blankValues))
```

Important implication:

- `starter` tray lines never appear in the compiled answer
- blank values are interpolated into the final code
- indentation is normalized to 4 spaces per indent level in the compiled answer

## Parsed PrairieLearn Outputs

### Canonical outputs

File: `pl-faded-parsons.py`

`parse()` writes:

- `data["submitted_answers"][answers_name] = student_code`
- `pl.add_submitted_file(data, out_filename, base64(student_code))`

These are the modern outputs other graders/elements should rely on.

## Panel-Specific Data

### Question panel

Data source:

- current markup or reconstructed prior submission

Data sink:

- hidden raw state inputs

### Submission panel

File: `pl-faded-parsons-submission.mustache`

Uses:

- `code`

Expected intent:

- display the compiled student code and grader feedback

### Answer panel

File: `pl-faded-parsons-answer.mustache`

Uses:

- `solution_path`

Expected intent:

- display the reference solution file

## Name Linkage Summary

These names must stay aligned:

### Hidden input names

- Mustache:
  - `{{answers_name}}.main`
  - `{{answers_name}}.log`
- JS:
  - `storage`
  - `logStorage`
  - `loggingEnabled`
- Python:
  - `raw_submitted_answers[f"{answers_name}.main"]`
  - `raw_submitted_answers[f"{answers_name}.log"]`

### Raw line schema

- JS:
  - `indent`
  - `codeSnippets`
  - `blankValues`
- Python:
  - `state_line["indent"]`
  - `state_line["codeSnippets"]`
  - `state_line["blankValues"]`

### Mustache line schema

- Python:
  - `{"code": {...}}`
  - `{"blank": {...}}`
- Mustache partial:
  - `{{#code}}`
  - `{{#blank}}`

### Child element rules

- `pre-text` and `post-text`
  - only allowed when `format="one-tray"` or the legacy alias `format="no-code"`
  - at most one of each
- `code-lines`
  - at most one direct child
  - required when `format="one-tray"` or the legacy alias `format="no-code"`

## Audit Notes And Inconsistencies

These are the main inconsistencies found during review.

### 1. `code_lines.txt` fallback is effectively broken

File: `pl-faded-parsons.py`

`self._options` is read before it is assigned:

- uses `self._options["question_path"]`
- assigns `self._options = data["options"]` later

Because this is inside a broad `try/except`, the fallback silently drops to `self._element.text` instead of ever reading `serverFilesQuestion/code_lines.txt`.

### 2. Submission and answer panels hardcode Python highlighting

Files:

- `pl-faded-parsons-submission.mustache`
- `pl-faded-parsons-answer.mustache`

Both templates hardcode `language="python"` instead of using the element's `language` attribute.

### 3. Submitted file encoding is ASCII-only

File: `pl-faded-parsons.py`

`parse()` base64-encodes with:

```python
s.encode("ascii")
```

Non-ASCII student code will fail here even though PrairieLearn/file submission paths should be able to carry UTF-8 text.

### 4. Accessibility tray-count text uses the wrong comparison

File: `pl-faded-parsons.js`

`codelineAriaDetails()` checks:

```js
trays > 1
```

but `trays` is a jQuery object. This should almost certainly be `trays.length > 1`.

### 5. Log-storage error path references an undefined variable

File: `pl-faded-parsons.js`

`addLogEntry()` builds an error message using `selector`, but no such variable exists in scope.

### 6. Clipboard starter-line comment prefixes appear reversed

File: `pl-faded-parsons.js`

`asPlaintext()` uses `# ` for C/Java-style languages and `// ` otherwise, which looks backward.

### 7. JS comments refer to old/nonexistent Python types

File: `pl-faded-parsons.js`

Comments mention:

- `Line.from_pl_data`
- `ProblemState.from_pl_data`

Those do not match the current Python implementation and can mislead future maintenance.

### 8. Code-line template contains a suspicious extra attribute

File: `pl-faded-parsons-code-line.mustache`

Blank inputs include:

```html
.=""
```

This looks accidental and should be reviewed.

### 9. `source-file-name` is unquoted in the answer template

File: `pl-faded-parsons-answer.mustache`

This may be harmless for simple paths, but quoted attributes are safer and more consistent.

## Recommended Canonical Contract

If future cleanup happens, the clean contract to preserve is:

1. Raw UI state lives only in:
   - `raw_submitted_answers["<answers-name>.main"]`
   - `raw_submitted_answers["<answers-name>.log"]`
2. Parsed canonical code lives only in:
   - `submitted_answers["<answers-name>"]`
3. File-based autograders consume:
   - the submitted file added via `pl.add_submitted_file(...)`
4. Legacy flat keys remain compatibility-only, not primary behavior.
