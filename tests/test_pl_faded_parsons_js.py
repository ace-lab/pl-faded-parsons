import json
import subprocess
import textwrap
from pathlib import Path
import unittest


ELEMENT_DIR = Path(__file__).resolve().parents[1]
JS_PATH = ELEMENT_DIR / "pl-faded-parsons.js"


def run_js(expression: str) -> dict:
    script = textwrap.dedent(
        f"""
        const fs = require('fs');
        const vm = require('vm');

        const source = fs.readFileSync({json.dumps(str(JS_PATH))}, 'utf8');
        const sandbox = {{
          window: {{}},
          console: {{
            log() {{}},
            error() {{}},
            warn() {{}},
          }},
          navigator: {{}},
          document: {{
            createElement(tag) {{
              if (tag === 'canvas') {{
                return {{
                  getContext() {{
                    return {{
                      font: '',
                      measureText() {{
                        return {{ width: 8 }};
                      }},
                    }};
                  }},
                }};
              }}
              return {{
                appendChild() {{}},
                innerHTML: '',
              }};
            }},
          }},
        }};

        function jqueryMock() {{
          return {{
            length: 0,
          }};
        }}
        jqueryMock.extend = Object.assign;
        jqueryMock.fn = {{ extend() {{}} }};
        sandbox.jQuery = jqueryMock;
        sandbox.$ = jqueryMock;

        vm.createContext(sandbox);
        vm.runInContext(source, sandbox);
        sandbox.ParsonsGlobalUISettings = sandbox.window.ParsonsGlobalUISettings;
        const result = {expression};
        process.stdout.write(JSON.stringify(result));
        """
    )

    completed = subprocess.run(
        ["node", "-e", script],
        check=True,
        capture_output=True,
        text=True,
    )
    return json.loads(completed.stdout)


class TestPlFadedParsonsJsHelpers(unittest.TestCase):
    def test_build_widget_config_merges_defaults(self):
        result = run_js(
            "sandbox.window.ParsonsWidgetHelpers.buildWidgetConfig({ canIndent: false, extra: 1 })"
        )

        self.assertEqual(result["xIndent"], 4)
        self.assertFalse(result["canIndent"])
        self.assertTrue(result["prettyPrint"])
        self.assertEqual(result["extra"], 1)

    def test_build_toolbar_help_content_joins_lines(self):
        result = run_js("sandbox.window.ParsonsWidgetHelpers.buildToolbarHelpContent()")

        self.assertIn("Arrow Keys: Select<br>", result)
        self.assertIn("(Shift+)Enter: Enter Prev/Next Blank", result)

    def test_key_motion_data_tracks_modifier_keys(self):
        result = run_js(
            "sandbox.window.ParsonsWidgetHelpers.getKeyMotionData({ altKey: true, ctrlKey: false, metaKey: true, shiftKey: false, key: 'ArrowRight' })"
        )

        self.assertTrue(result["moveCodeline"])
        self.assertTrue(result["moveToEnd"])
        self.assertTrue(result["jumpForward"])
        self.assertTrue(result["moveForward"])

    def test_clamp_indent_respects_bounds(self):
        result = run_js(
            textwrap.dedent(
                """
                (() => {
                  sandbox.ParsonsGlobalUISettings.maxIndentLevel = 5;
                  return [
                    sandbox.window.ParsonsWidgetHelpers.clampIndent(-2),
                    sandbox.window.ParsonsWidgetHelpers.clampIndent(3),
                    sandbox.window.ParsonsWidgetHelpers.clampIndent(99),
                  ];
                })()
                """
            )
        )

        self.assertEqual(result, [0, 3, 5])

    def test_get_indent_at_drag_position_clamps_dragged_indent(self):
        result = run_js(
            textwrap.dedent(
                """
                (() => {
                  sandbox.ParsonsGlobalUISettings.maxIndentLevel = 5;
                  const widget = {
                    config: { xIndent: 4 },
                    getCodelineIndent() { return 2; },
                  };
                  const ui = {
                    item: [
                      {
                        },
                    ],
                    position: { left: 96 },
                  };
                  ui.item.parent = () => ({ position: () => ({ left: 0 }) });
                  return sandbox.window.ParsonsWidgetHelpers.getIndentAtDragPosition(widget, ui);
                })()
                """
            )
        )

        self.assertEqual(result, 5)

    def test_landed_in_another_tray_detects_tray_change(self):
        result = run_js(
            textwrap.dedent(
                """
                (() => {
                  const currentTray = { id: 'current-tray' };
                  const ui = {
                    item: {
                      parent() {
                        return [currentTray];
                      },
                    },
                  };
                  return [
                    sandbox.window.ParsonsWidgetHelpers.landedInAnotherTray({ target: currentTray }, ui),
                    sandbox.window.ParsonsWidgetHelpers.landedInAnotherTray({ target: { id: 'other-tray' } }, ui),
                  ];
                })()
                """
            )
        )

        self.assertEqual(result, [False, True])

    def test_setup_toolbar_bindings_wires_help_copy_and_dark_actions(self):
        result = run_js(
            textwrap.dedent(
                """
                (() => {
                  const calls = {};
                  const help = {
                    popover(options) {
                      calls.help = options;
                      return this;
                    },
                  };
                  const copy = {
                    popover(options) {
                      calls.copyPopover = options;
                      return this;
                    },
                    on(handlers) {
                      calls.copyClick = handlers.click;
                      return this;
                    },
                  };
                  const dark = {
                    on(handlers) {
                      calls.darkClick = handlers.click;
                      return this;
                    },
                  };
                  const toolbar = {
                    find(selector) {
                      if (selector === '.widget-help') return help;
                      if (selector === '.widget-copy') return copy;
                      if (selector === '.widget-dark') return dark;
                      throw new Error(selector);
                    },
                  };
                  sandbox.$ = (selector) => {
                    if (selector === '#toolbar') return toolbar;
                    return { length: 0, exists() { return false; } };
                  };
                  sandbox.jQuery = sandbox.$;
                  sandbox.navigator.clipboard = {
                    writeText(text) {
                      calls.copiedText = text;
                      return { catch() {} };
                    },
                  };
                  const Widget = sandbox.ParsonsWidget || sandbox.window.ParsonsWidget;
                  const widget = {
                    config: { toolbar: '#toolbar' },
                    asPlaintext() {
                      return 'plain-text';
                    },
                    toggleDarkmode() {
                      calls.darkToggled = true;
                    },
                  };
                  Widget.prototype.setupToolbarBindings.call(widget);
                  calls.copyClick();
                  calls.darkClick();
                  return {
                    helpTitle: calls.help.title,
                    helpContent: calls.help.content,
                    copiedText: calls.copiedText,
                    darkToggled: calls.darkToggled,
                    copyTrigger: calls.copyPopover.trigger,
                  };
                })()
                """
            )
        )

        self.assertEqual(result["helpTitle"], "Faded Parsons Help")
        self.assertIn("Arrow Keys: Select<br>", result["helpContent"])
        self.assertEqual(result["copiedText"], "plain-text")
        self.assertTrue(result["darkToggled"])
        self.assertEqual(result["copyTrigger"], "focus")

    def test_setup_tray_sortables_uses_global_config_and_callbacks(self):
        result = run_js(
            textwrap.dedent(
                """
                (() => {
                  const captured = {};
                  function makeItem() {
                    const parentObj = {};
                    const parentWrapper = {
                      0: parentObj,
                      position() {
                        return { left: 0 };
                      },
                    };
                    return {
                      0: { id: 'line-1' },
                      parent() {
                        return parentWrapper;
                      },
                      addClass() {},
                      removeClass() {},
                    };
                  }
                  const starter = {
                    sortable(options) {
                      captured.starter = options;
                    },
                  };
                  const solution = {
                    sortable(options) {
                      captured.solution = options;
                    },
                  };
                  sandbox.$ = (selector) => {
                    if (selector === '#starter') return starter;
                    if (selector === '#solution') return solution;
                    return {
                      length: 0,
                      exists() { return false; },
                    };
                  };
                  sandbox.jQuery = sandbox.$;
                  sandbox.ParsonsGlobalUISettings.allowIndentingInStarterTray = true;
                  const logTags = [];
                  const widget = {
                    config: {
                      starterList: '#starter',
                      solutionList: '#solution',
                      canIndent: true,
                      xIndent: 4,
                      onSortableUpdate() {},
                    },
                    activeSortablePlaceholder: null,
                    setCodelineInMotion() {},
                    syncSortablePlaceholder() {},
                    updateIndent(line, indent, absolute) {
                      captured.updatedIndent = { line, indent, absolute };
                    },
                    storeStudentProgress() {
                      captured.stored = true;
                    },
                    addLogEntry(tag) {
                      logTags.push(tag);
                    },
                    codelineLogEntry() {
                      return { stub: true };
                    },
                  };
                  widget.getCodelineIndent = () => 4;
                  const Widget = sandbox.ParsonsWidget || sandbox.window.ParsonsWidget;
                  Widget.prototype.setupTraySortables.call(widget);
                  const item = makeItem();
                  captured.starter.start({}, { placeholder: 'ph', item });
                  captured.starter.sort({}, { item, position: { left: 32 } });
                  const parent = item.parent()[0];
                  captured.starter.receive({}, { item, position: { left: 32 } });
                  captured.starter.stop({ target: parent }, { item });
                  captured.solution.receive({}, { item, position: { left: 32 } });
                  captured.solution.stop({ target: parent }, { item, position: { left: 32 } });
                  return {
                    starterGrid: captured.starter.grid,
                    solutionGrid: captured.solution.grid,
                    logs: logTags,
                    updatedIndent: captured.updatedIndent,
                    stored: captured.stored,
                    placeholder: widget.activeSortablePlaceholder,
                  };
                })()
                """
            )
        )

        self.assertEqual(result["starterGrid"], [32, 1])
        self.assertEqual(result["solutionGrid"], [32, 1])
        self.assertIn("removeOutput", result["logs"])
        self.assertIn("addOutput", result["logs"])
        self.assertIn("moveOutput", result["logs"])
        self.assertTrue(result["stored"])
        self.assertEqual(result["updatedIndent"]["indent"], 5)

    def test_sync_sortable_placeholder_updates_active_placeholder(self):
        result = run_js(
            textwrap.dedent(
                """
                (() => {
                  const calls = [];
                  const placeholder = {
                    exists() { return true; },
                    empty() { calls.push('empty'); return this; },
                    css(name, value) { calls.push([name, value]); return this; },
                  };
                  const widget = {
                    activeSortablePlaceholder: placeholder,
                    getCodelineIndent() { return 3; },
                  };
                  const Widget = sandbox.ParsonsWidget || sandbox.window.ParsonsWidget;
                  Widget.prototype.syncSortablePlaceholder.call(widget, { id: 'line' });
                  return calls;
                })()
                """
            )
        )

        self.assertEqual(result, ["empty", ["--pl-faded-parsons-indent", 3]])

    def test_setup_core_dom_helpers_exposes_dom_adapters(self):
        result = run_js(
            textwrap.dedent(
                """
                (() => {
                  const widget = {
                    config: {},
                  };
                  const Widget = sandbox.ParsonsWidget || sandbox.window.ParsonsWidget;
                  Widget.prototype.setupCoreDomHelpers.call(widget);
                  const line = {
                    classes: new Set(),
                    attrs: {},
                  };
                  sandbox.$ = (value) => {
                    if (value === line) {
                      return {
                        attr(name, maybeValue) {
                          if (maybeValue === undefined) return line.attrs[name];
                          line.attrs[name] = maybeValue;
                          return this;
                        },
                        toggleClass(name, enabled) {
                          if (enabled) line.classes.add(name); else line.classes.delete(name);
                          return this;
                        },
                        hasClass(name) {
                          return line.classes.has(name);
                        },
                        find() {
                          return {
                            length: 1,
                          };
                        },
                      };
                    }
                    if (value && value.classes instanceof Set) {
                      return {
                        hasClass(name) {
                          return value.classes.has(name);
                        },
                      };
                    }
                    return {
                      find() {
                        return {
                          length: 1,
                        };
                      },
                    };
                  };
                  widget.setCodelineInMotion(line, true);
                  return {
                    dragState: widget.getCodelineInMotion(line),
                    placeholder: widget.isSortablePlaceholder({ classes: new Set(['ui-sortable-placeholder']) }),
                    blankQueryLength: widget.findBlanksIn(line).length,
                    ariaGrabbed: line.attrs['aria-grabbed'],
                  };
                })()
                """
            )
        )

        self.assertTrue(result["dragState"])
        self.assertTrue(result["placeholder"])
        self.assertEqual(result["blankQueryLength"], 1)
        self.assertTrue(result["ariaGrabbed"])

    def test_setup_initial_gui_state_runs_redraw_storage_and_autosize(self):
        result = run_js(
            textwrap.dedent(
                """
                (() => {
                  const blanks = [{ value: 'x' }, { value: 'yy' }];
                  const widget = {
                    config: { main: '#main' },
                    redrawTabStops() {
                      sandbox.calls.redrawn = true;
                    },
                    storeStudentProgress() {
                      sandbox.calls.stored = true;
                    },
                    findBlanksIn() {
                      return {
                        each(fn) {
                          blanks.forEach((blank, idx) => fn(idx, blank));
                        },
                      };
                    },
                    autoSizeBlank(blank) {
                      sandbox.calls.sized.push(blank.value);
                    },
                  };
                  sandbox.calls = { sized: [] };
                  const Widget = sandbox.ParsonsWidget || sandbox.window.ParsonsWidget;
                  Widget.prototype.setupInitialGuiState.call(widget);
                  return sandbox.calls;
                })()
                """
            )
        )

        self.assertTrue(result["redrawn"])
        self.assertTrue(result["stored"])
        self.assertEqual(result["sized"], ["x", "yy"])

    def test_setup_accessibility_bindings_sets_aria_hooks(self):
        result = run_js(
            textwrap.dedent(
                """
                (() => {
                  const attrs = { descriptor: {}, details: {}, main: {} };
                  const codelines = [{
                    attrs: {},
                  }];
                  const blanks = [{
                    attrs: {},
                  }];
                  const main = {
                    find(selector) {
                      if (selector === 'li.codeline') {
                        return {
                          attr(name, value) {
                            codelines.forEach((line) => { line.attrs[name] = value; });
                            return this;
                          },
                        };
                      }
                      return {
                        attr() { return this; },
                      };
                    },
                  };
                  sandbox.$ = (selector) => {
                    if (selector === '#descriptor') {
                      return {
                        css(name, value) { attrs.descriptor[name] = value; return this; },
                        attr(name) { return name === 'id' ? 'descriptor-id' : null; },
                      };
                    }
                    if (selector === '#details') {
                      return {
                        css(name, value) { attrs.details[name] = value; return this; },
                        attr(name) { return name === 'id' ? 'details-id' : null; },
                      };
                    }
                    if (selector === '#main') return main;
                    return {
                      attr() { return this; },
                      find() { return { attr() { return this; } }; },
                    };
                  };
                  sandbox.jQuery = sandbox.$;
                  sandbox.ParsonsGlobalUISettings.showAriaDescriptor = true;
                  const widget = {
                    config: { ariaDescriptor: '#descriptor', ariaDetails: '#details', main: '#main' },
                    findBlanksIn() {
                      return {
                        attr(name, value) {
                          blanks.forEach((blank) => { blank.attrs[name] = value; });
                          return this;
                        },
                      };
                    },
                  };
                  const Widget = sandbox.ParsonsWidget || sandbox.window.ParsonsWidget;
                  Widget.prototype.setupAccessibilityBindings.call(widget);
                  return { descriptor: attrs.descriptor, details: attrs.details, codeline: codelines[0].attrs, blank: blanks[0].attrs };
                })()
                """
            )
        )

        self.assertEqual(result["descriptor"]["display"], "inline-block")
        self.assertEqual(result["details"]["display"], "inline-block")
        self.assertEqual(result["codeline"]["aria-labelledby"], "descriptor-id")
        self.assertEqual(result["blank"]["aria-details"], "details-id")

    def test_focus_codeline_enters_first_or_last_blank(self):
        result = run_js(
            textwrap.dedent(
                """
                (() => {
                  const calls = [];
                  const firstBlank = { focus() { calls.push('first'); }, or() { return this; } };
                  const lastBlank = { focus() { calls.push('last'); }, or() { return this; } };
                  const line = { focus() { calls.push('line'); } };
                  const widget = {
                    enterBlankOnCodelineFocus: true,
                    findBlanksIn() {
                      return {
                        first() { return firstBlank; },
                        last() { return lastBlank; },
                      };
                    },
                  };
                  sandbox.$ = (value) => ({
                    exists() { return !!value; },
                    focus() { value.focus(); return this; },
                    or(other) { return other; },
                  });
                  const Widget = sandbox.ParsonsWidget || sandbox.window.ParsonsWidget;
                  Widget.prototype.focusCodeline.call(widget, line, true);
                  widget.enterBlankOnCodelineFocus = false;
                  Widget.prototype.focusCodeline.call(widget, line, false);
                  return calls;
                })()
                """
            )
        )

        self.assertEqual(result, ["first", "line"])

    def test_find_horizontal_target_chooses_closest_line(self):
        result = run_js(
            textwrap.dedent(
                """
                (() => {
                  const near = { getBoundingClientRect() { return { top: 20, bottom: 40 }; } };
                  const far = { getBoundingClientRect() { return { top: 100, bottom: 120 }; } };
                  const target = {
                    0: near,
                    exists() { return true; },
                  };
                  const tray = {
                    find(selector) {
                      if (selector !== 'li.codeline') throw new Error(selector);
                      return {
                        minBy(fn) {
                          fn(0, near);
                          fn(1, far);
                          return target;
                        },
                      };
                    },
                  };
                  sandbox.$ = (value) => ({
                    find() {
                      return {
                        minBy() {
                          return target;
                        },
                      };
                    },
                  });
                  const widget = {};
                  const Widget = sandbox.ParsonsWidget || sandbox.window.ParsonsWidget;
                  const resultTarget = Widget.prototype.findHorizontalTarget.call(widget, near, tray);
                  return {
                    found: resultTarget.found,
                    targetIsLower: resultTarget.targetIsLower,
                    sameObject: resultTarget.target === target,
                  };
                })()
                """
            )
        )

        self.assertTrue(result["found"])
        self.assertFalse(result["targetIsLower"])
        self.assertTrue(result["sameObject"])

    def test_move_horizontally_focuses_target_without_moving(self):
        result = run_js(
            textwrap.dedent(
                """
                (() => {
                  const focusCalls = [];
                  const currentLine = { id: 'current' };
                  const targetLine = { focus() { focusCalls.push('target'); } };
                  const tray = {
                    has() {
                      return { exists() { return true; } };
                    },
                  };
                  const codeboxes = {
                    length: 2,
                    toArray() { return [tray, tray]; },
                    eq() { return { find() { return { exists() { return true; } }; } }; },
                  };
                  const codebox = {
                    find(selector) {
                      if (selector !== '.codeline-list') return this;
                      return {
                        find() {
                          return {
                            minBy() {
                              return {
                                0: targetLine,
                                exists() { return true; },
                              };
                            },
                          };
                        },
                      };
                    },
                  };
                  sandbox.$ = (value) => {
                    if (value === '#main') {
                      return {
                        find(selector) {
                          if (selector === '.codeline-tray') return codeboxes;
                          return this;
                        },
                      };
                    }
                    if (value === currentLine) {
                      return {
                        has() { return { exists() { return true; } }; },
                        focus() { focusCalls.push('current'); return this; },
                      };
                    }
                    if (value === targetLine) {
                      return {
                        focus() { focusCalls.push('target'); return this; },
                      };
                    }
                    return {
                      has() { return { exists() { return false; } }; },
                      focus() { return this; },
                    };
                  };
                  const widget = {
                    config: { main: '#main' },
                    findHorizontalTarget() {
                      return { found: true, targetIsLower: false, target: targetLine };
                    },
                    focusCodeline(line) {
                      focusCalls.push(line === targetLine ? 'target' : 'other');
                    },
                  };
                  const Widget = sandbox.ParsonsWidget || sandbox.window.ParsonsWidget;
                  Widget.prototype.moveHorizontally.call(widget, currentLine, { moveForward: true, moveCodeline: false });
                  return focusCalls;
                })()
                """
            )
        )

        self.assertEqual(result, ["target"])

    def test_move_cursor_in_blank_horizontally_advances_when_at_edge(self):
        result = run_js(
            textwrap.dedent(
                """
                (() => {
                  const calls = [];
                  const blank = {
                    value: 'abc',
                    selectionStart: 3,
                    selectionEnd: 3,
                    setSelectionRange(start, end) { calls.push([start, end]); },
                  };
                  const widget = {
                    findBlanksIn() {
                      return {
                        length: 1,
                        get() { return blank; },
                        eq() { return blank; },
                      };
                    },
                    moveHorizontally() {
                      calls.push('move');
                    },
                  };
                  const e = { preventDefault() { calls.push('prevent'); } };
                  const Widget = sandbox.ParsonsWidget || sandbox.window.ParsonsWidget;
                  const moved = Widget.prototype.moveCursorInBlankHorizontally.call(widget, e, {}, 0, { moveForward: true });
                  return { moved, calls };
                })()
                """
            )
        )

        self.assertTrue(result["moved"])
        self.assertEqual(result["calls"], ["prevent", "move"])

    def test_jump_to_next_blank_wraps_around(self):
        result = run_js(
            textwrap.dedent(
                """
                (() => {
                  const focusCalls = [];
                  const blanks = [
                    { focus() { focusCalls.push(0); } },
                    { focus() { focusCalls.push(1); } },
                  ];
                  const widget = {
                    config: { main: '#main' },
                    findBlanksIn() {
                      return {
                        length: blanks.length,
                        index(blank) { return blanks.indexOf(blank); },
                        eq(idx) { return blanks[idx]; },
                      };
                    },
                  };
                  const Widget = sandbox.ParsonsWidget || sandbox.window.ParsonsWidget;
                  Widget.prototype.jumpToNextBlank.call(widget, blanks[1], { jumpForward: true });
                  Widget.prototype.jumpToNextBlank.call(widget, blanks[0], { jumpForward: false });
                  return focusCalls;
                })()
                """
            )
        )

        self.assertEqual(result, [0, 1])

    def test_move_vertically_focuses_neighbor_or_reorders(self):
        result = run_js(
            textwrap.dedent(
                """
                (() => {
                  const calls = [];
                  const current = {
                    parent() {
                      return {
                        children() {
                          return {
                            last() { return { focus() { calls.push('last'); } }; },
                            first() { return { focus() { calls.push('first'); } }; },
                          };
                        },
                      };
                    },
                  };
                  const widget = {
                    focusCodeline() { calls.push('focus'); },
                  };
                  sandbox.$ = (value) => {
                    if (value === current) {
                      return {
                        parent() { return current.parent(); },
                        next() { return { exists() { return true; } }; },
                        prev() { return { exists() { return true; } }; },
                      };
                    }
                    return {
                      or() { return this; },
                      focus() { return this; },
                    };
                  };
                  const Widget = sandbox.ParsonsWidget || sandbox.window.ParsonsWidget;
                  Widget.prototype.moveVertically.call(widget, current, { moveForward: true, moveToEnd: false, moveCodeline: false });
                  return calls;
                })()
                """
            )
        )

        self.assertEqual(result, ["focus"])

    def test_on_codeline_keydown_handles_navigation_keys(self):
        result = run_js(
            textwrap.dedent(
                """
                (() => {
                  const calls = [];
                  const codeline = {};
                  const widget = {
                    config: { starter: '#starter' },
                    updateIndent(line, delta, absolute) { calls.push(['indent', delta, absolute]); },
                    moveHorizontally(line, motionData) { calls.push(['horizontal', motionData.moveForward]); },
                    moveVertically(line, motionData) { calls.push(['vertical', motionData.moveForward]); },
                    setCodelineInMotion(line, inMotion) { calls.push(['motion', inMotion]); },
                    findBlanksIn() {
                      return { first() { calls.push(['blank-first']); return { focus() {} }; } };
                    },
                  };
                  sandbox.ParsonsGlobalUISettings.allowIndentingInStarterTray = false;
                  sandbox.$ = (value) => ({
                    is() { return true; },
                    has() { return { exists() { return true; } }; },
                    blur() { calls.push('blur'); return this; },
                  });
                  const Widget = sandbox.ParsonsWidget || sandbox.window.ParsonsWidget;
                  Widget.prototype.onCodelineKeydown.call(widget, { key: 'Tab', preventDefault() { calls.push('prevent'); }, altKey: false, ctrlKey: false, metaKey: false, shiftKey: false }, codeline);
                  Widget.prototype.onCodelineKeydown.call(widget, { key: 'Enter', preventDefault() { calls.push('enter'); } }, codeline);
                  Widget.prototype.onCodelineKeydown.call(widget, { key: 'Escape', preventDefault() { calls.push('escape'); } }, codeline);
                  return calls;
                })()
                """
            )
        )

        self.assertIn(["horizontal", True], result)
        self.assertIn("prevent", result)
        self.assertIn("blur", result)

    def test_on_blank_keydown_handles_tab_enter_escape_and_cursor_motion(self):
        result = run_js(
            textwrap.dedent(
                """
                (() => {
                  const calls = [];
                  const codeline = {};
                  const blank = { value: 'abc', selectionStart: 3, selectionEnd: 3 };
                  const nextBlank = {
                    focus() { calls.push('next'); return this; },
                    setSelectionRange(start, end) { calls.push(['range', start, end]); },
                    value: 'x',
                  };
                  const widget = {
                    config: { main: '#main' },
                    updateIndent(line, delta, absolute) { calls.push(['indent', delta, absolute]); },
                    moveVertically(line, motionData) { calls.push(['vertical', motionData.moveForward]); },
                    moveHorizontally(line, motionData) { calls.push(['horizontal', motionData.moveForward]); },
                    moveCursorInBlankHorizontally(e, line, blankIdx, motionData) {
                      calls.push(['cursor', blankIdx, motionData.moveForward]);
                    },
                    jumpToNextBlank(blankArg, motionData) {
                      calls.push(['jump', motionData.jumpForward]);
                    },
                    findBlanksIn() {
                      return {
                        length: 2,
                        index() { return 0; },
                        eq(idx) { return idx === 0 ? blank : nextBlank; },
                      };
                    },
                  };
                  sandbox.ParsonsGlobalUISettings.alwaysIndentOnTab = true;
                  sandbox.$ = (value) => ({
                    focus() { calls.push('focus'); return this; },
                    is() { return true; },
                  });
                  const Widget = sandbox.ParsonsWidget || sandbox.window.ParsonsWidget;
                  Widget.prototype.onBlankKeydown.call(widget, { key: 'Tab', preventDefault() { calls.push('prevent-tab'); }, shiftKey: false, altKey: false, ctrlKey: false, metaKey: false }, codeline, blank);
                  Widget.prototype.onBlankKeydown.call(widget, { key: 'Enter', preventDefault() { calls.push('prevent-enter'); } }, codeline, blank);
                  Widget.prototype.onBlankKeydown.call(widget, { key: 'Escape', stopPropagation() { calls.push('stop'); } }, codeline, blank);
                  Widget.prototype.onBlankKeydown.call(widget, { key: 'ArrowRight', preventDefault() { calls.push('prevent-right'); }, altKey: false, ctrlKey: false, metaKey: false, shiftKey: false }, codeline, blank);
                  return calls;
                })()
                """
            )
        )

        self.assertIn(["indent", 1, False], result)
        self.assertIn(["jump", True], result)
        self.assertIn(["cursor", 0, True], result)
        self.assertIn("focus", result)
        self.assertIn("stop", result)

    def test_setup_interactivity_bindings_wires_logging_and_handlers(self):
        result = run_js(
            textwrap.dedent(
                """
                (() => {
                  const handlers = {};
                  const blankHandlers = {};
                  const codeline = { target: 'line', value: 'line' };
                  const blank = { target: 'blank', value: 'abc' };
                  const allBlanks = {
                    each(fn) {
                      fn(0, blank);
                      return this;
                    },
                    on(eventMap) {
                      blankHandlers.edit = eventMap.input;
                      return this;
                    },
                  };
                  const codelines = {
                    each(fn) {
                      fn(0, codeline);
                      return this;
                    },
                    on(eventMap) {
                      handlers.codeline = eventMap;
                      return this;
                    },
                  };
                  const trays = {
                    each(fn) {
                      fn(0, {
                        find(selector) {
                          if (selector === 'li.codeline') {
                            return {
                              each(fn2) {
                                fn2(0, codeline);
                                return this;
                              },
                            };
                          }
                          return this;
                        },
                      });
                      return this;
                    },
                  };
                  sandbox.$ = (selector) => {
                    if (selector === '#main') {
                      return {
                        find(q) {
                          if (q === 'li.codeline') return codelines;
                          if (q === '.codeline-tray') return trays;
                          return allBlanks;
                        },
                      };
                    }
                    if (selector === codeline) {
                      return {
                        attr() { return this; },
                        on(eventMap) { handlers.codeline = eventMap; return this; },
                        find() { return allBlanks; },
                        is() { return true; },
                        blur() { return this; },
                        parent() { return { children() { return { last() { return this; }, first() { return this; } }; } }; },
                      };
                    }
                    if (selector === blank) {
                      return {
                        on(eventMap) { blankHandlers.blank = eventMap; return this; },
                        attr(name, value) { if (value === undefined) return 'blank-id'; return this; },
                        val() { return 'abc'; },
                        focus() { return this; },
                        setSelectionRange() {},
                        selectionStart: 3,
                        selectionEnd: 3,
                      };
                    }
                    return {
                      find() { return allBlanks; },
                      attr() { return this; },
                      on() { return this; },
                      val() { return 'abc'; },
                    };
                  };
                  sandbox.jQuery = sandbox.$;
                  const widget = {
                    config: { main: '#main', onBlankUpdate() {} },
                    enterBlankOnCodelineFocus: false,
                    updateAriaInfo() { sandbox.calls.aria = (sandbox.calls.aria || 0) + 1; },
                    storeStudentProgress() { sandbox.calls.stored = true; },
                    addLogEntry(tag) { sandbox.calls.logTag = tag; },
                    updateIndent() {},
                  };
                  sandbox.calls = {};
                  const Widget = sandbox.ParsonsWidget || sandbox.window.ParsonsWidget;
                  Widget.prototype.setupCoreDomHelpers.call(widget);
                  Widget.prototype.setupInteractivityBindings.call(widget);
                  return { calls: sandbox.calls, hasHandlers: !!handlers.codeline, hasBlank: !!blankHandlers.blank, hasEdit: !!blankHandlers.edit };
                })()
                """
            )
        )

        self.assertTrue(result["hasHandlers"])
        self.assertTrue(result["hasEdit"])
        self.assertEqual(result["calls"]["logTag"], "problemOpened")


if __name__ == "__main__":
    unittest.main()
