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
  const value = await parsons(page, widgetId).inputs.main.inputValue();
  return JSON.parse(value);
}


export async function parseStoredLog(page, widgetId = "uuid-123") {
  const value = await parsons(page, widgetId).inputs.log.inputValue();
  return JSON.parse(value);
}

export function parsons(page, uuid = "uuid-123") {
  const rootSelector = `#pl-faded-parsons-${uuid}`;
  const controlsSelector = `#widget-controls-${uuid}`;

  return {
    root: page.locator(rootSelector),
    trays: {
      starter: page.locator(`#starter-code-${uuid}`),
      solution: page.locator(`#solution-${uuid}`),
      all: page.locator(`${rootSelector} .codeline-tray`),
    },
    codelines: {
      starter: page.locator(`#ol-starter-code-${uuid} > li.codeline`),
      solution: page.locator(`#ol-solution-${uuid} > li.codeline`),
      all: page.locator(`${rootSelector} li.codeline`),
    },
    inputs: {
      main: page.locator(`${rootSelector} > input.main`),
      log: page.locator(`${rootSelector} > input.log`),
    },
    blanks: {
      all: page.locator(`${rootSelector} input.parsons-blank`),
      missing: page.locator(`${rootSelector} input.parsons-blank-missing`),
    },
    controls: {
      all: page.locator(controlsSelector),
      copy: page.locator(`${controlsSelector} .widget-copy`),
      help: page.locator(`${controlsSelector} .widget-help`),
    },
    text: {
      pre: page.locator(`${rootSelector} .pre-text-wrapper`),
      post: page.locator(`${rootSelector} .post-text-wrapper`),
    },
    aria: {
      descriptor: page.locator(`#pl-faded-parsons-aria-descriptor-${uuid}`),
      details: page.locator(`#pl-faded-parsons-aria-details-${uuid}`),
    },
  };
}
