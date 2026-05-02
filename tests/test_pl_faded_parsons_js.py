import json
import subprocess
import textwrap
from pathlib import Path
import unittest


ELEMENT_DIR = Path.cwd()
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
        self.assertEqual(result["visualIndent"], 0)
        self.assertTrue(result["prettyPrint"])
        self.assertEqual(result["extra"], 1)

    def test_apply_visual_indent_subtracts_one_from_positive_values_on_trays(self):
        result = run_js(
            textwrap.dedent(
                """
                (() => {
                  const calls = [];
                  sandbox.$ = sandbox.jQuery = (selector) => ({
                    find(query) {
                      return {
                        css(name, value) {
                          calls.push([selector, query, name, value]);
                        },
                      };
                    },
                  });

                  sandbox.window.ParsonsWidget.prototype.applyVisualIndent.call({
                    config: { main: '#widget', visualIndent: 3 },
                  });

                  return calls;
                })()
                """
            )
        )

        self.assertEqual(
            result,
            [
                ["#widget", ".codeline-tray", "--pl-faded-parsons-visual-indent-correction", "1ch"],
                ["#widget", ".codeline-tray", "--pl-faded-parsons-visual-indent", 3],
            ],
        )

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
                  const Widget = sandbox.window.ParsonsWidget || sandbox.window.ParsonsWidget;
                  const widget = Object.create(Widget.prototype);
                  widget.config = { maxIndentLevel: 5 };
                  return [
                    widget.clampIndent(-2),
                    widget.clampIndent(3),
                    widget.clampIndent(99),
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
                  const Widget = sandbox.window.ParsonsWidget || sandbox.window.ParsonsWidget;
                  const widget = Object.create(Widget.prototype);
                  widget.config = { xIndent: 4, maxIndentLevel: 5 };
                  widget.getCodelineIndent = () => 2;
                  const tray = {
                    0: {
                      getBoundingClientRect() {
                        return { left: 0 };
                      },
                    },
                  };
                  const ui = {
                    item: [
                      {
                        },
                      ],
                    helper: [{
                      getBoundingClientRect() {
                        return { left: 96 };
                      },
                    }],
                    position: { left: 96 },
                  };
                  ui.item.parent = () => tray;
                  return widget.getIndentAtDragPosition(ui);
                })()
                """
            )
        )

        self.assertEqual(result, 5)

    def test_get_indent_at_drag_position_uses_item_parent_by_default(self):
        result = run_js(
            textwrap.dedent(
                """
                (() => {
                  const Widget = sandbox.window.ParsonsWidget || sandbox.window.ParsonsWidget;
                  const widget = Object.create(Widget.prototype);
                  widget.config = { xIndent: 4, maxIndentLevel: 5 };
                  widget.getCodelineIndent = () => 0;
                  const tray = {
                    0: {
                      getBoundingClientRect() {
                        return { left: 100 };
                      },
                    },
                  };
                  const ui = {
                    item: [{
                      style: {},
                    }],
                    helper: [{
                      getBoundingClientRect() {
                        return { left: 164 };
                      },
                    }],
                    position: { left: 164 },
                  };
                  ui.item.parent = () => tray;
                  return widget.getIndentAtDragPosition(ui);
                })()
                """
            )
        )

        self.assertEqual(result, 2)

    def test_get_indent_at_drag_position_uses_placeholder_tray_when_dragging_across_trays(self):
        result = run_js(
            textwrap.dedent(
                """
                (() => {
                  const startTray = {
                    0: {
                      getBoundingClientRect() {
                        return { left: 0 };
                      },
                    },
                  };
                  const liveTray = {
                    0: {
                      getBoundingClientRect() {
                        return { left: 100 };
                      },
                    },
                  };
                  const Widget = sandbox.window.ParsonsWidget || sandbox.window.ParsonsWidget;
                  const widget = Object.create(Widget.prototype);
                  widget.config = { xIndent: 4, maxIndentLevel: 5 };
                  widget.getCodelineIndent = () => 0;
                  const ui = {
                    item: [{
                      style: {},
                    }],
                    helper: [{
                      getBoundingClientRect() {
                        return { left: 164 };
                      },
                    }],
                    position: { left: 164 },
                    placeholder: {
                      parent() {
                        return liveTray;
                      },
                    },
                  };
                  ui.item.parent = () => startTray;
                  return widget.getIndentAtDragPosition(ui);
                })()
                """
            )
        )

        self.assertEqual(result, 2)

    def test_get_indent_at_drag_position_falls_back_when_parent_has_no_position(self):
        result = run_js(
            textwrap.dedent(
                """
                (() => {
                  const Widget = sandbox.window.ParsonsWidget || sandbox.window.ParsonsWidget;
                  const widget = Object.create(Widget.prototype);
                  widget.config = { xIndent: 4, maxIndentLevel: 5 };
                  widget.getCodelineIndent = () => 1;
                  const ui = {
                    item: [{
                      style: {},
                    }],
                    position: { left: 0 },
                  };
                  ui.item.parent = () => ({ position() { return undefined; } });
                  return widget.getIndentAtDragPosition(ui);
                })()
                """
            )
        )

        self.assertEqual(result, 1)

    def test_get_indent_at_drag_position_survives_positioned_tray(self):
        result = run_js(
            textwrap.dedent(
                """
                (() => {
                  const Widget = sandbox.window.ParsonsWidget || sandbox.window.ParsonsWidget;
                  const widget = Object.create(Widget.prototype);
                  widget.config = { xIndent: 4, maxIndentLevel: 5 };
                  widget.getCodelineIndent = () => 0;
                  const tray = {
                    0: {
                      getBoundingClientRect() {
                        return { left: 240 };
                      },
                    },
                  };
                  const ui = {
                    item: [{
                      style: {},
                    }],
                    helper: [{
                      getBoundingClientRect() {
                        return { left: 324 };
                      },
                    }],
                    position: { left: 80 },
                  };
                  ui.item.parent = () => tray;
                  return widget.getIndentAtDragPosition(ui);
                })()
                """
            )
        )

        self.assertEqual(result, 2)

    def test_landed_in_another_tray_detects_tray_change(self):
        result = run_js(
            textwrap.dedent(
                """
                (() => {
                  const startTray = { id: 'start-tray' };
                  const endTray = { id: 'end-tray' };
                  const ui = {
                    item: [{
                      __plFppDragStartTray: startTray,
                    }],
                  };
                  ui.item.parent = () => [endTray];
                  return [
                    sandbox.window.ParsonsWidgetHelpers.draggedFromAnotherTray(ui),
                    sandbox.window.ParsonsWidgetHelpers.landedInAnotherTray({ target: endTray }, ui),
                    sandbox.window.ParsonsWidgetHelpers.landedInAnotherTray({ target: { id: 'other-tray' } }, ui),
                  ];
                })()
                """
            )
        )

        self.assertEqual(result, [True, True, True])

    def test_landed_in_another_tray_falls_back_to_event_target_when_drag_origin_missing(self):
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

    def test_setup_toolbar_bindings_wires_help_and_copy_actions(self):
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
                    attr(name, value) {
                      calls.helpAttr = [name, value];
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
                  const toolbar = {
                    find(selector) {
                      if (selector === '.widget-help') return help;
                      if (selector === '.widget-copy') return copy;
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
                  };
                  Widget.prototype.setupToolbarBindings.call(widget);
                  calls.copyClick();
                  return {
                    helpTitle: calls.help.title,
                    helpContent: calls.help.content,
                    helpAriaDescription: calls.helpAttr,
                    copiedText: calls.copiedText,
                    copyTrigger: calls.copyPopover.trigger,
                  };
                })()
                """
            )
        )

        self.assertEqual(result["helpTitle"], "Faded Parsons Help")
        self.assertIn("Arrow Keys: Select<br>", result["helpContent"])
        self.assertEqual(result["helpAriaDescription"][0], "aria-description")
        self.assertIn("Arrow Keys: Select", result["helpAriaDescription"][1])
        self.assertEqual(result["copiedText"], "plain-text")
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
                  const Widget = sandbox.window.ParsonsWidget || sandbox.window.ParsonsWidget;
                  const widget = Object.create(Widget.prototype);
                  widget.config = {
                    starterList: '#starter',
                    solutionList: '#solution',
                    canIndent: true,
                    xIndent: 4,
                    maxIndentLevel: 5,
                    onSortableUpdate() {},
                  };
                  widget.activeSortablePlaceholder = null;
                  widget.setCodelineInMotion = () => {};
                  widget.syncSortablePlaceholder = () => {};
                  widget.updateIndent = (line, indent, absolute) => {
                    captured.updatedIndent = { line, indent, absolute };
                  };
                  widget.storeStudentProgress = () => {
                    captured.stored = true;
                  };
                  widget.addLogEntry = (tag) => {
                    logTags.push(tag);
                  };
                  widget.codelineLogEntry = () => {
                    return { stub: true };
                  };
                  widget.getCodelineIndent = () => 4;
                  Widget.prototype.setupTraySortables.call(widget);
                  const item = makeItem();
                  captured.starter.start({}, {
                    placeholder: {
                      addClass() {},
                    },
                    item,
                  });
                  captured.starter.sort({}, { item, position: { left: 32 } });
                  const parent = item.parent()[0];
                  captured.starter.receive({}, { item, position: { left: 32 } });
                  captured.starter.stop({ target: parent }, { item });
                  captured.solution.receive({}, { item, position: { left: 32 } });
                  captured.solution.stop({ target: parent }, { item, position: { left: 32 } });
                  return {
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

    def test_sync_sortable_placeholder_allows_zero_indent(self):
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
                  Widget.prototype.syncSortablePlaceholder.call(widget, { id: 'line' }, 0);
                  return calls;
                })()
                """
            )
        )

        self.assertEqual(result, ["empty", ["--pl-faded-parsons-indent", 0]])

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
                    attr(name, value) {
                      attrs.main[name] = value;
                      return this;
                    },
                    find(selector) {
                      if (selector === 'li.codeline') {
                        return {
                          each(fn) {
                            codelines.forEach((line, idx) => fn(idx, line));
                            return this;
                          },
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
                  return { descriptor: attrs.descriptor, details: attrs.details, main: attrs.main, codeline: codelines[0].attrs, blank: blanks[0].attrs };
                })()
                """
            )
        )

        self.assertEqual(result["descriptor"]["display"], "inline-block")
        self.assertEqual(result["details"]["display"], "inline-block")
        self.assertEqual(result["main"]["aria-labelledby"], "descriptor-id")
        self.assertEqual(result["main"]["aria-details"], "details-id")
        self.assertEqual(result["codeline"]["aria-labelledby"], "descriptor-id")
        self.assertEqual(result["blank"]["aria-details"], "details-id")

    def test_setup_accessibility_bindings_marks_blank_free_lines_as_code_lines(self):
        result = run_js(
            textwrap.dedent(
                """
                (() => {
                  const codeline = { attrs: {} };
                  const main = {
                    attr(name, value) {
                      this[name] = value;
                      return this;
                    },
                    find(selector) {
                      if (selector === 'li.codeline') {
                        return {
                          each(fn) {
                            fn(0, codeline);
                            return this;
                          },
                          attr(name, value) {
                            codeline.attrs[name] = value;
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
                        css() { return this; },
                        attr(name) { return name === 'id' ? 'descriptor-id' : null; },
                      };
                    }
                    if (selector === '#details') {
                      return {
                        css() { return this; },
                        attr(name) { return name === 'id' ? 'details-id' : null; },
                      };
                    }
                    if (selector === '#main') return main;
                    if (selector === codeline) {
                      return {
                        attr(name, value) {
                          if (value !== undefined) {
                            codeline.attrs[name] = value;
                          }
                          return this;
                        },
                      };
                    }
                    return {
                      attr() { return this; },
                      find() { return { attr() { return this; } }; },
                    };
                  };
                  sandbox.jQuery = sandbox.$;
                  const widget = {
                    config: { ariaDescriptor: '#descriptor', ariaDetails: '#details', main: '#main' },
                    findBlanksIn() {
                      return {
                        length: 0,
                        attr() { return this; },
                      };
                    },
                  };
                  const Widget = sandbox.ParsonsWidget || sandbox.window.ParsonsWidget;
                  Widget.prototype.setupAccessibilityBindings.call(widget);
                  return codeline.attrs;
                })()
                """
            )
        )

        self.assertEqual(result["aria-roledescription"], "code line")

    def test_update_aria_info_mentions_root_capture_controls(self):
        result = run_js(
            textwrap.dedent(
                """
                (() => {
                  const descriptor = { text(value) { this.value = value; return this; } };
                  const details = { text(value) { this.value = value; return this; } };
                  const widget = {
                    config: { ariaDescriptor: '#descriptor', ariaDetails: '#details' },
                    codelineAriaDescription() {
                      return 'line description';
                    },
                    codelineAriaDetails() {
                      return 'line details';
                    },
                  };
                  sandbox.$ = (selector) => {
                    if (selector === '#descriptor') return descriptor;
                    if (selector === '#details') return details;
                    return { text() { return this; } };
                  };
                  sandbox.jQuery = sandbox.$;
                  const Widget = sandbox.ParsonsWidget || sandbox.window.ParsonsWidget;
                  Widget.prototype.updateAriaInfo.call(widget, null, false);
                  return { descriptor: descriptor.value, details: details.value };
                })()
                """
            )
        )

        self.assertIn("press enter on the widget to focus the lines of code", result["descriptor"])
        self.assertIn("escape to exit", result["details"])

    def test_setup_interactivity_bindings_enters_capture_from_widget_root(self):
        result = run_js(
            textwrap.dedent(
                """
                (() => {
                  const events = {};
                  const firstLine = { id: 'first-line' };
                  const codelineList = {
                    each(fn) {
                      fn(0, firstLine);
                      return this;
                    },
                    attr(name, value) {
                      events.codelineTabStop = [name, value];
                      return this;
                    },
                    on(handlers) {
                      events.codelineHandlers = handlers;
                      return this;
                    },
                  };
                  const main = {
                    on(handlers) {
                      events.mainHandlers = handlers;
                      return this;
                    },
                    find(selector) {
                      if (selector === 'li.codeline') return codelineList;
                      if (selector === 'input.parsons-blank') {
                        return {
                          on() { return this; },
                          each() { return this; },
                        };
                      }
                      if (selector === '.codeline-tray') {
                        return {
                          each() { return this; },
                        };
                      }
                      throw new Error(selector);
                    },
                  };
                  sandbox.$ = (selector) => {
                    if (selector === '#main') return main;
                    if (selector === firstLine) {
                      return {
                        is() { return false; },
                        closest() { return { exists() { return false; } }; },
                        find() { return { on() { return this; }, each() { return this; } }; },
                      };
                    }
                    return {
                      on() { return this; },
                      each() { return this; },
                      find() { return this; },
                      closest() { return { exists() { return false; } }; },
                      is() { return false; },
                    };
                  };
                  sandbox.jQuery = sandbox.$;
                  const widget = {
                    config: { main: '#main' },
                    codelineCaptureActive: false,
                    enterBlankOnCodelineFocus: false,
                    getSolutionLines() {
                      return [firstLine];
                    },
                    getSourceLines() {
                      return [];
                    },
                    focusCodeline(line) {
                      events.focusedLine = line;
                      events.enterBlankAtFocus = this.enterBlankOnCodelineFocus;
                    },
                    updateAriaInfo() {},
                    setCodelineInMotion() {},
                    storeStudentProgress() {},
                    addLogEntry(tag) {
                      events.logTag = tag;
                    },
                    findBlanksIn() {
                      return {
                        on() { return this; },
                        each() { return this; },
                      };
                    },
                  };
                  const Widget = sandbox.ParsonsWidget || sandbox.window.ParsonsWidget;
                  Widget.prototype.setupCoreDomHelpers.call(widget);
                  widget.enterCodelineCapture = Widget.prototype.enterCodelineCapture;
                  Widget.prototype.setupInteractivityBindings.call(widget);
                  events.mainHandlers.keydown({
                    key: 'Enter',
                    target: main,
                    currentTarget: main,
                    preventDefault() { events.prevented = true; },
                  });
                  return {
                    capture: widget.codelineCaptureActive,
                    enterBlank: widget.enterBlankOnCodelineFocus,
                    focused: events.focusedLine === firstLine,
                    enterBlankAtFocus: events.enterBlankAtFocus,
                    codelineTabStop: events.codelineTabStop,
                    prevented: events.prevented,
                  };
                })()
                """
            )
        )

        self.assertTrue(result["capture"])
        self.assertFalse(result["enterBlank"])
        self.assertTrue(result["focused"])
        self.assertFalse(result["enterBlankAtFocus"])
        self.assertEqual(result["codelineTabStop"], ["tabindex", "0"])
        self.assertTrue(result["prevented"])

    def test_enter_codeline_capture_announces_mode_change(self):
        result = run_js(
            textwrap.dedent(
                """
                (() => {
                  const live = {
                    text(value) {
                      this.value = value;
                      return this;
                    },
                  };
                  const widget = {
                    config: { ariaDetails: '#details' },
                    codelineCaptureActive: false,
                    enterBlankOnCodelineFocus: true,
                    setCodelinesTabStops(active) {
                      this.tabStops = active;
                    },
                    getSolutionLines() {
                      return [null];
                    },
                    getSourceLines() {
                      return [null];
                    },
                    focusCodeline(line) {
                      this.focused = line;
                    },
                  };
                  sandbox.$ = (selector) => {
                    if (selector === '#details') return live;
                    return { text() { return this; } };
                  };
                  sandbox.jQuery = sandbox.$;
                  const Widget = sandbox.ParsonsWidget || sandbox.window.ParsonsWidget;
                  widget.announceMode = Widget.prototype.announceMode;
                  Widget.prototype.enterCodelineCapture.call(widget);
                  return { message: live.value, tabStops: widget.tabStops, focused: widget.focused };
                })()
                """
            )
        )

        self.assertIn("Arrow-key mode on", result["message"])
        self.assertTrue(result["tabStops"])

    def test_escape_from_codeline_announces_tabbing_mode(self):
        result = run_js(
            textwrap.dedent(
                """
                (() => {
                  const live = {
                    text(value) {
                      this.value = value;
                      return this;
                    },
                  };
                  const widget = {
                    config: { ariaDetails: '#details' },
                    setCodelinesTabStops(active) {
                      this.tabStops = active;
                    },
                  };
                  sandbox.$ = (selector) => {
                    if (selector === '#details') return live;
                    if (selector === '#line') {
                      return {
                        is() { return true; },
                        blur() { this.blurred = true; return this; },
                      };
                    }
                    return { text() { return this; } };
                  };
                  sandbox.jQuery = sandbox.$;
                  const Widget = sandbox.ParsonsWidget || sandbox.window.ParsonsWidget;
                  widget.announceMode = Widget.prototype.announceMode;
                  Widget.prototype.onCodelineKeydown.call(widget, {
                    key: 'Escape',
                    preventDefault() {},
                  }, '#line');
                  return { message: live.value, tabStops: widget.tabStops };
                })()
                """
            )
        )

        self.assertIn("Tabbing mode on", result["message"])
        self.assertFalse(result["tabStops"])

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
                  const sourceLine = { id: 'source' };
                  const targetLine = { id: 'target', exists() { return true; } };
                  const target = {
                    0: targetLine,
                    exists() { return true; },
                    or() { return this; },
                  };
                  const targetLines = {
                    filter() { return this; },
                    eq(idx) {
                      return idx === 1
                        ? target
                        : { exists() { return false; }, or() { return this; } };
                    },
                    last() {
                      return target;
                    },
                  };
                  const tray = {
                    find(selector) {
                      if (selector !== 'li.codeline') throw new Error(selector);
                      return targetLines;
                    },
                  };
                  const widget = {
                    isSortablePlaceholder() { return false; },
                  };
                  sandbox.$ = (value) => ({
                    parent() {
                      return {
                        children() {
                          return {
                            filter() {
                              return {
                                index() {
                                  return 1;
                                },
                              };
                            },
                          };
                        },
                      };
                    },
                    find() {
                      return targetLines;
                    },
                    or() { return this; },
                  });
                  const Widget = sandbox.ParsonsWidget || sandbox.window.ParsonsWidget;
                  const resultTarget = Widget.prototype.findHorizontalTarget.call(widget, sourceLine, tray);
                  return {
                    found: resultTarget.found,
                    sameObject: resultTarget.target === target,
                  };
                })()
                """
            )
        )

        self.assertTrue(result["found"])
        self.assertTrue(result["sameObject"])

    def test_move_horizontally_focuses_target_without_moving(self):
        result = run_js(
            textwrap.dedent(
                """
                (() => {
                  const focusCalls = [];
                  const currentLine = { id: 'current' };
                  const targetLine = { id: 'target', focus() { focusCalls.push('target'); } };
                  const newTray = {
                    find() {
                      return {
                        filter() { return this; },
                        eq() { return targetLine; },
                        last() { return targetLine; },
                      };
                    },
                  };
                  sandbox.$ = (value) => {
                    if (value === '#main') {
                      return {
                        find(selector) {
                          if (selector === '.codeline-tray') {
                            return {
                              length: 2,
                              toArray() {
                                return [
                                  { has() { return { exists() { return true; } }; } },
                                  { has() { return { exists() { return true; } }; } },
                                ];
                              },
                              eq(idx) {
                                return idx === 1 ? newTray : {};
                              },
                            };
                          }
                          return this;
                        },
                        or() { return this; },
                      };
                    }
                    if (value === newTray) {
                      return {
                        append(line) {
                          inserted.push(['append', line.id]);
                        },
                        focus() { return this; },
                        or() { return this; },
                      };
                    }
                    if (value === newTray) {
                      return {
                        append(line) {
                          inserted.push(['append', line.id]);
                        },
                        or() { return this; },
                        focus() { return this; },
                      };
                    }
                    if (value === currentLine) {
                      return {
                        parent() {
                          return {
                            children() {
                              return {
                                filter() {
                                  return {
                                    index() {
                                      return 1;
                                    },
                                  };
                                },
                              };
                            },
                          };
                        },
                        or() { return this; },
                        focus() { focusCalls.push('current'); return this; },
                      };
                    }
                    if (value && typeof value.has === 'function') {
                      return {
                        has(line) { return value.has(line); },
                        or() { return this; },
                        focus() { return this; },
                      };
                    }
                    return { focus() { return this; }, or() { return this; } };
                  };
                  sandbox.document.activeElement = currentLine;
                  const widget = {
                    config: { main: '#main' },
                    isSortablePlaceholder() { return false; },
                    findHorizontalTarget() {
                      return { found: true, target: targetLine };
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

    def test_find_horizontal_target_falls_back_to_last_line(self):
        result = run_js(
            textwrap.dedent(
                """
                (() => {
                  const sourceLine = { id: 'source' };
                  const lastLine = { id: 'last', exists() { return true; } };
                  const targetLines = {
                    length: 1,
                    eq(idx) {
                      return {
                        exists() { return false; },
                      };
                    },
                    last() {
                      return lastLine;
                    },
                    filter() {
                      return this;
                    },
                  };
                  sandbox.$ = (value) => ({
                    parent() {
                      return {
                        children() {
                          return {
                            filter() {
                              return {
                                index() {
                                  return 3;
                                },
                              };
                            },
                          };
                        },
                      };
                    },
                    find() {
                      return targetLines;
                    },
                    or() { return this; },
                  });
                  const widget = {
                    isSortablePlaceholder() { return false; },
                  };
                  const Widget = sandbox.ParsonsWidget || sandbox.window.ParsonsWidget;
                  const resultTarget = Widget.prototype.findHorizontalTarget.call(widget, sourceLine, {});
                  return resultTarget.target.id === 'last';
                })()
                """
            )
        )

        self.assertTrue(result)

    def test_move_horizontally_inserts_before_same_row_target(self):
        result = run_js(
            textwrap.dedent(
                """
                (() => {
                  const calls = [];
                  const currentLine = { id: 'current' };
                  const targetLine = {
                    id: 'target',
                    exists() { return true; },
                    focus() { calls.push('target-focus'); return this; },
                  };
                  const inserted = [];
                  const newTray = {
                    find() {
                      return {
                        filter() { return this; },
                        eq() { return targetLine; },
                        last() { return targetLine; },
                      };
                    },
                    append(line) {
                      inserted.push(['append', line.id]);
                    },
                  };
                  sandbox.$ = (value) => {
                    if (value === '#main') {
                      return {
                        find(selector) {
                          if (selector === '.codeline-tray') {
                            return {
                              length: 2,
                              toArray() {
                                return [
                                  { has() { return { exists() { return true; } }; } },
                                  { has() { return { exists() { return true; } }; } },
                                ];
                              },
                              eq(idx) { return idx === 1 ? newTray : {}; },
                            };
                          }
                          return this;
                        },
                        or() { return this; },
                        focus() { return this; },
                      };
                    }
                    if (value === currentLine) {
                      return {
                        parent() {
                          return {
                            children() {
                              return {
                                filter() {
                                  return {
                                    index() { return 1; },
                                  };
                                },
                              };
                            },
                          };
                        },
                        insertBefore(target) {
                          inserted.push(['before', target.id]);
                        },
                        or() { return this; },
                      };
                    }
                    if (value && typeof value.has === 'function') {
                      return {
                        has(line) { return value.has(line); },
                        or() { return this; },
                        focus() { return this; },
                      };
                    }
                    return {
                      focus() { return this; },
                      or() { return this; },
                    };
                  };
                  sandbox.document.activeElement = currentLine;
                  const widget = {
                    config: { main: '#main' },
                    isSortablePlaceholder() { return false; },
                    findHorizontalTarget() {
                      return { found: true, target: targetLine };
                    },
                    focusCodeline() {},
                  };
                  const Widget = sandbox.ParsonsWidget || sandbox.window.ParsonsWidget;
                  Widget.prototype.moveHorizontally.call(widget, currentLine, { moveForward: true, moveCodeline: true });
                  return inserted;
                })()
                """
            )
        )

        self.assertEqual(result, [["before", "target"]])

    def test_move_horizontally_appends_when_source_row_exceeds_destination(self):
        result = run_js(
            textwrap.dedent(
                """
                (() => {
                  const currentLine = { id: 'current' };
                  const inserted = [];
                  const trayList = {
                    append(line) {
                      inserted.push(['append', line.id]);
                    },
                  };
                  const newTray = {
                    find() {
                      return trayList;
                    },
                  };
                  sandbox.$ = (value) => {
                    if (value === '#main') {
                      return {
                        find(selector) {
                          if (selector === '.codeline-tray') {
                            return {
                              length: 2,
                              toArray() {
                                return [
                                  { has() { return { exists() { return true; } }; } },
                                  { has() { return { exists() { return true; } }; } },
                                ];
                              },
                              eq(idx) { return idx === 1 ? newTray : {}; },
                            };
                          }
                          return this;
                        },
                        or() { return this; },
                      };
                    }
                    if (value === currentLine) {
                      return {
                        parent() {
                          return {
                            children() {
                              return {
                                filter() {
                                  return {
                                    index() { return 2; },
                                  };
                                },
                              };
                            },
                          };
                        },
                        or() { return this; },
                        focus() { return this; },
                      };
                    }
                    if (value === trayList) {
                      return {
                        append(line) {
                          inserted.push(['append', line.id]);
                        },
                        or() { return this; },
                        focus() { return this; },
                      };
                    }
                    if (value && typeof value.has === 'function') {
                      return {
                        has(line) { return value.has(line); },
                        or() { return this; },
                        focus() { return this; },
                      };
                    }
                    return {
                      focus() { return this; },
                      or() { return this; },
                    };
                  };
                  sandbox.document.activeElement = currentLine;
                  const widget = {
                    config: { main: '#main' },
                    isSortablePlaceholder() { return false; },
                    findHorizontalTarget() {
                      return { found: false, target: { exists() { return false; }, or() { return this; } } };
                    },
                    focusCodeline() {},
                  };
                  const Widget = sandbox.ParsonsWidget || sandbox.window.ParsonsWidget;
                  Widget.prototype.moveHorizontally.call(widget, currentLine, { moveForward: true, moveCodeline: true });
                  return inserted;
                })()
                """
            )
        )

        self.assertEqual(result, [["append", "current"]])

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

    def test_move_cursor_in_blank_horizontally_sets_selection_before_focus(self):
        result = run_js(
            textwrap.dedent(
                """
                (() => {
                  const calls = [];
                  const firstBlank = {
                    value: 'abc',
                    selectionStart: 3,
                    selectionEnd: 3,
                  };
                  const nextBlank = {
                    value: 'xyz',
                    setSelectionRange(start, end) { calls.push(['range', start, end]); },
                  };
                  const widget = {
                    findBlanksIn() {
                      return {
                        length: 2,
                        get(idx) { return idx === 0 ? firstBlank : nextBlank; },
                        eq(idx) {
                          return {
                            each(fn) { fn(0, nextBlank); return this; },
                            focus() { calls.push('focus'); return this; },
                          };
                        },
                      };
                    },
                  };
                  const e = { preventDefault() { calls.push('prevent'); } };
                  const Widget = sandbox.ParsonsWidget || sandbox.window.ParsonsWidget;
                  Widget.prototype.moveCursorInBlankHorizontally.call(widget, e, {}, 0, { moveForward: true });
                  return calls;
                })()
                """
            )
        )

        self.assertEqual(result, ["prevent", ["range", 0, 0], "focus"])

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
                    setCodelinesTabStops(active) { calls.push(['tabstops', active]); },
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

    def test_codeline_keydown_does_not_overwrite_focus_announcement(self):
        result = run_js(
            textwrap.dedent(
                """
                (() => {
                  const calls = [];
                  const line1 = { id: 'line1' };
                  const line2 = { id: 'line2' };
                  const codelineList = {
                    each(fn) {
                      fn(0, line1);
                      fn(1, line2);
                      return this;
                    },
                    on(eventMap) {
                      this.handlers = eventMap;
                      return this;
                    },
                  };
                  const main = {
                    on() { return this; },
                    find(selector) {
                      if (selector === 'li.codeline') return codelineList;
                      if (selector === 'input.parsons-blank') {
                        return { on() { return this; }, each() { return this; } };
                      }
                      if (selector === '.codeline-tray') return { each() { return this; } };
                      throw new Error(selector);
                    },
                  };
                  sandbox.$ = (selector) => {
                    if (selector === '#main') return main;
                    if (selector === line1) {
                      return {
                        is(query) { return query === ':focus'; },
                        closest() { return { exists() { return false; } }; },
                        find() { return { on() { return this; }, each() { return this; } }; },
                      };
                    }
                    if (selector === line2) {
                      return {
                        is(query) { return query === ':focus'; },
                        closest() { return { exists() { return false; } }; },
                        find() { return { on() { return this; }, each() { return this; } }; },
                      };
                    }
                    return {
                      on() { return this; },
                      each() { return this; },
                      find() { return this; },
                      closest() { return { exists() { return false; } }; },
                      is() { return false; },
                    };
                  };
                  sandbox.jQuery = sandbox.$;
                  const widget = {
                    config: { main: '#main' },
                    enterBlankOnCodelineFocus: false,
                    setCodelineInMotion() {},
                    storeStudentProgress() {},
                    addLogEntry() {},
                    moveHorizontally() {
                      codelineList.handlers.focus({ currentTarget: line2 });
                    },
                    updateAriaInfo(line) {
                      calls.push(line === line1 ? 'line1' : 'line2');
                    },
                  };
                  const Widget = sandbox.ParsonsWidget || sandbox.window.ParsonsWidget;
                  widget.onCodelineKeydown = Widget.prototype.onCodelineKeydown;
                  Widget.prototype.setupCoreDomHelpers.call(widget);
                  widget.setCodelineInMotion = () => {};
                  Widget.prototype.setupInteractivityBindings.call(widget);
                  calls.length = 0;
                  codelineList.handlers.keydown({
                    key: 'ArrowRight',
                    preventDefault() {},
                    altKey: false,
                    ctrlKey: false,
                    metaKey: false,
                    shiftKey: false,
                  });
                  return calls;
                })()
                """
            )
        )

        self.assertEqual(result, ["line2"])

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
                        on() { return this; },
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
