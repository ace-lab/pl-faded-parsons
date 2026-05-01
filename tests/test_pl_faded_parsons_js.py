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
        sandbox.ParsonsGlobal = sandbox.window.ParsonsGlobal;
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
            "sandbox.window.ParsonsWidgetHelpers.keyMotionData({ altKey: true, ctrlKey: false, metaKey: true, shiftKey: false, key: 'ArrowRight' })"
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
                  sandbox.ParsonsGlobal.uiConfig.maxIndentLevel = 5;
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
                  sandbox.ParsonsGlobal.charWidthInPx = 8;
                  sandbox.ParsonsGlobal.uiConfig.maxIndentLevel = 5;
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


if __name__ == "__main__":
    unittest.main()
