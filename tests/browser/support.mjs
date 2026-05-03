import { spawnSync } from "node:child_process";
import fs from "node:fs";
import path from "node:path";
import { createRequire } from "node:module";
import { fileURLToPath } from "node:url";


const require = createRequire(import.meta.url);
const browserDir = path.dirname(fileURLToPath(import.meta.url));
export const elementDir = path.resolve(browserDir, "..", "..");
const renderScript = path.join(browserDir, "render-question.py");


function readText(filePath) {
  return fs.readFileSync(filePath, "utf8");
}


function inlineScript(source) {
  return `<script>${source.replaceAll("</script>", "<\\/script>")}</script>`;
}


function loadAssetText(modulePath) {
  return readText(require.resolve(modulePath));
}


const jquerySource = loadAssetText("jquery/dist/jquery.min.js");
const jqueryUiSource = loadAssetText("jquery-ui-dist/jquery-ui.min.js");
const touchPunchSource = loadAssetText("jquery-ui-touch-punch/jquery.ui.touch-punch.min.js");
const prettifySource = readText(path.join(elementDir, "prettify.js"));
const widgetSource = readText(path.join(elementDir, "pl-faded-parsons.js"));


export function renderQuestion(elementHtml, dataOverrides = {}, uuid = "uuid-123") {
  const payload = Buffer.from(
    JSON.stringify({ elementHtml, dataOverrides, uuid }),
    "utf8",
  ).toString("base64");

  for (const python of [process.env.PYTHON, "python3", "python"].filter(Boolean)) {
    const completed = spawnSync(python, [renderScript, payload], {
      encoding: "utf8",
    });

    if (completed.status === 0) {
      return completed.stdout;
    }

    if (completed.error?.code === "ENOENT") {
      continue;
    }

    const stderr = completed.stderr?.trim();
    const stdout = completed.stdout?.trim();
    throw new Error(
      [
        `Failed to render pl-faded-parsons question HTML with ${python}.`,
        stderr ? `stderr:\n${stderr}` : null,
        stdout ? `stdout:\n${stdout}` : null,
      ]
        .filter(Boolean)
        .join("\n\n"),
    );
  }

  throw new Error("Could not find a working Python interpreter for the browser harness.");
}


export function buildBrowserHtml(renderedHtml) {
  return `<!doctype html>
<html lang="en">
  <head>
    <meta charset="utf-8">
    <script>
      window.__clipboardWrites = [];
      window.__alerts = [];
    </script>
    ${inlineScript(jquerySource)}
    ${inlineScript(jqueryUiSource)}
    ${inlineScript(touchPunchSource)}
    ${inlineScript(prettifySource)}
    ${inlineScript(widgetSource)}
    ${inlineScript(`
      (() => {
        const original = window.ParsonsWidget;
        window.__plWidgets = [];
        if (!window.jQuery.fn.popover) {
          window.jQuery.fn.popover = function(options) {
            this.each((_, element) => {
              element.__popoverOptions = options;
            });
            return this;
          };
        }
        window.ParsonsWidget = function(...args) {
          const instance = new original(...args);
          window.__plWidgets.push(instance);
          window.__lastWidget = instance;
          return instance;
        };
        window.ParsonsWidget.prototype = original.prototype;
        Object.setPrototypeOf(window.ParsonsWidget, original);
      })();
    `)}
  </head>
  <body>
    ${renderedHtml}
  </body>
</html>`;
}


export async function mountQuestion(page, elementHtml, dataOverrides = {}, uuid = "uuid-123") {
  const renderedHtml = renderQuestion(elementHtml, dataOverrides, uuid);
  await page.setContent(buildBrowserHtml(renderedHtml), {
    waitUntil: "load",
  });
  await page.waitForFunction((descriptorId) => {
    const descriptor = document.querySelector(descriptorId);
    return !!descriptor?.textContent?.trim();
  }, `#pl-faded-parsons-aria-descriptor-${uuid}`);
  await page.evaluate(() => {
    const clipboard = {
      writeText: async (text) => {
        window.__clipboardWrites.push(text);
      },
    };

    try {
      Object.defineProperty(navigator, "clipboard", {
        configurable: true,
        value: clipboard,
      });
    } catch {
      try {
        Object.defineProperty(Navigator.prototype, "clipboard", {
          configurable: true,
          value: clipboard,
        });
      } catch {
        window.__clipboardWrites.push("__clipboard-mock-failed__");
      }
    }

    window.alert = (message) => {
      window.__alerts.push(message);
    };
  });

  return {
    renderedHtml,
    widgetId: uuid,
  };
}


export async function parseStoredMain(page, widgetId = "uuid-123") {
  const value = await parsons(page, widgetId).inputs().main().inputValue();
  return JSON.parse(value);
}


export async function parseStoredLog(page, widgetId = "uuid-123") {
  const value = await parsons(page, widgetId).inputs().log().inputValue();
  return JSON.parse(value);
}

export function parsons(page, uuid = "uuid-123") {
  const rootSelector = `#pl-faded-parsons-${uuid}`;
  const traySelector = (name) => (name === "starter" ? `#starter-code-${uuid}` : `#solution-${uuid}`);
  const listSelector = (name) => (name === "starter" ? `#ol-starter-code-${uuid}` : `#ol-solution-${uuid}`);
  const controlsSelector = `#widget-controls-${uuid}`;

  return {
    root() {
      return page.locator(rootSelector);
    },
    trays() {
      return {
        starter() {
          return page.locator(traySelector("starter"));
        },
        solution() {
          return page.locator(traySelector("solution"));
        },
        all() {
          return page.locator(`${rootSelector} .codeline-tray`);
        },
      };
    },
    codelines() {
      return {
        starter() {
          return page.locator(`${listSelector("starter")} > li.codeline`);
        },
        solution() {
          return page.locator(`${listSelector("solution")} > li.codeline`);
        },
        all() {
          return page.locator(`${rootSelector} li.codeline`);
        },
      };
    },
    inputs() {
      return {
        main() {
          return page.locator(`${rootSelector} > input.main`);
        },
        log() {
          return page.locator(`${rootSelector} > input.log`);
        },
      };
    },
    blanks() {
      return {
        all() {
          return page.locator(`${rootSelector} input.parsons-blank`);
        },
        missing() {
          return page.locator(`${rootSelector} input.parsons-blank-missing`);
        },
      };
    },
    controls() {
      return {
        all() {
          return page.locator(controlsSelector);
        },
        copy() {
          return page.locator(`${controlsSelector} .widget-copy`);
        },
        help() {
          return page.locator(`${controlsSelector} .widget-help`);
        },
      };
    },
    text() {
      return {
        pre() {
          return page.locator(`${rootSelector} .pre-text-wrapper`);
        },
        post() {
          return page.locator(`${rootSelector} .post-text-wrapper`);
        },
      };
    },
    aria() {
      return {
        descriptor() {
          return page.locator(`#pl-faded-parsons-aria-descriptor-${uuid}`);
        },
        details() {
          return page.locator(`#pl-faded-parsons-aria-details-${uuid}`);
        },
      };
    },
  };
}

export function tray(page, uuid = "uuid-123") {
  return parsons(page, uuid).trays();
}

export function codelines(page, uuid = "uuid-123") {
  return parsons(page, uuid).codelines();
}
