import { spawnSync } from "node:child_process";
import fs from "node:fs";
import path from "node:path";
import { createRequire } from "node:module";
import { fileURLToPath } from "node:url";


const require = createRequire(import.meta.url);
const browserDir = path.dirname(fileURLToPath(import.meta.url));
export const elementDir = path.resolve(browserDir, "..", "..");
const elementInfo = JSON.parse(readText(path.join(elementDir, "info.json")));
const browserDependencyNames = [
  "jquery",
  ...(elementInfo.dependencies?.nodeModulesScripts ?? []),
  ...(elementInfo.dependencies?.elementScripts ?? []),
];
const renderScript = path.join(browserDir, "render-question.py");
const parseScript = path.join(browserDir, "parse-question.py");


function readText(filePath) {
  return fs.readFileSync(filePath, "utf8");
}


function inlineScript(source) {
  return `<script>${source.replaceAll("</script>", "<\\/script>")}</script>`;
}


function loadAssetText(modulePath) {
  return readText(require.resolve(modulePath));
}


function loadDependencySource(depName) {
  try {
    if (depName === "jquery") {
      return loadAssetText("jquery/dist/jquery.min.js");
    }

    if (elementInfo.dependencies?.nodeModulesScripts?.includes(depName)) {
      return loadAssetText(depName);
    }

    if (elementInfo.dependencies?.elementScripts?.includes(depName)) {
      return readText(path.join(elementDir, depName));
    }
  } catch (error) {
    throw new Error(
      `Failed to load browser dependency "${depName}": ${error instanceof Error ? error.message : String(error)}`,
    );
  }

  throw new Error(`Browser dependency "${depName}" is not declared in info.json`);
}


const browserDependencySources = Object.fromEntries(
  browserDependencyNames.map((depName) => [depName, loadDependencySource(depName)]),
);


function runPythonHelper(scriptPath, payload, failureLabel) {
  const encodedPayload = Buffer.from(JSON.stringify(payload), "utf8").toString("base64");

  for (const python of [process.env.PYTHON, "python3", "python"].filter(Boolean)) {
    const completed = spawnSync(python, [scriptPath, encodedPayload], {
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
        `${failureLabel} with ${python}.`,
        stderr ? `stderr:\n${stderr}` : null,
        stdout ? `stdout:\n${stdout}` : null,
      ]
        .filter(Boolean)
        .join("\n\n"),
    );
  }

  throw new Error("Could not find a working Python interpreter for the browser harness.");
}


/** Render the PrairieLearn question HTML for a given element snapshot. */
export function renderQuestion(elementHtml, dataOverrides = {}, uuid = "uuid-123") {
  return runPythonHelper(
    renderScript,
    { elementHtml, dataOverrides, uuid },
    "Failed to render pl-faded-parsons question HTML",
  );
}


/** Run the PrairieLearn parse lifecycle against authored element HTML. */
export function parseQuestion(
  elementHtml,
  dataOverrides = {},
  uuid = "uuid-123",
) {
  const output = runPythonHelper(
    parseScript,
    { elementHtml, dataOverrides, uuid },
    "Failed to parse pl-faded-parsons question HTML",
  );
  return JSON.parse(output);
}


/** Collect live input values from the mounted widget into raw-submission form. */
export async function collectRawSubmittedAnswers(page, widgetId = "uuid-123") {
  return parsons(page, widgetId).root.evaluate((root) => {
    const rawSubmittedAnswers = {};
    root.querySelectorAll("input[name]").forEach((input) => {
      rawSubmittedAnswers[input.name] = input.value;
    });
    return rawSubmittedAnswers;
  });
}


/** Clone the mounted widget DOM and preserve current input values in markup. */
export async function getHydratedQuestionHtml(page, widgetId = "uuid-123") {
  return parsons(page, widgetId).root.evaluate((root) => {
    const clone = root.cloneNode(true);
    const sourceInputs = root.querySelectorAll("input");
    const clonedInputs = clone.querySelectorAll("input");

    sourceInputs.forEach((input, index) => {
      const clonedInput = clonedInputs[index];
      if (clonedInput) {
        clonedInput.setAttribute("value", input.value);
      }
    });

    return clone.outerHTML;
  });
}


/** Parse the mounted widget using the original author HTML and live inputs. */
export async function parseQuestionFromPage(
  page,
  elementHtml,
  dataOverrides = {},
  widgetId = "uuid-123",
) {
  const rawSubmittedAnswers = await collectRawSubmittedAnswers(page, widgetId);
  return parseQuestion(
    elementHtml,
    { ...dataOverrides, rawSubmittedAnswers },
    widgetId,
  );
}


/** Assemble the standalone HTML shell used to host the browser harness. */
export function buildBrowserHtml(renderedHtml) {
  return `<!doctype html>
<html lang="en">
  <head>
    <meta charset="utf-8">
    <script>
      window.__clipboardWrites = [];
      window.__alerts = [];
    </script>
    ${browserDependencyNames.map((depName) => inlineScript(browserDependencySources[depName])).join("\n    ")}
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


/**
 * Mount a rendered question into Playwright and install clipboard/alert mocks.
 */
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


/** Read and decode the widget's hidden `.main` submission field. */
export async function parseStoredMain(page, widgetId = "uuid-123") {
  const value = await parsons(page, widgetId).inputs.main.inputValue();
  return JSON.parse(value);
}


/** Read and decode the widget's hidden `.log` submission field. */
export async function parseStoredLog(page, widgetId = "uuid-123") {
  const value = await parsons(page, widgetId).inputs.log.inputValue();
  return JSON.parse(value);
}

/** Build a locator map for the rendered `pl-faded-parsons` widget. */
export function parsons(page, uuid = "uuid-123") {
  const rootSelector = `#pl-faded-parsons-${uuid}`;
  const controlsSelector = `#widget-controls-${uuid}`;

  return {
    get root() {
      return page.locator(rootSelector);
    },
    starter: {
      get tray() {
        return page.locator(`#starter-code-${uuid}`);
      },
      get codelines() {
        return page.locator(`#ol-starter-code-${uuid} > li.codeline`);
      },
    },
    solution: {
      get tray() {
        return page.locator(`#solution-${uuid}`);
      },
      get codelines() {
        return page.locator(`#ol-solution-${uuid} > li.codeline`);
      },
    },
    all: {
      get trays() {
        return page.locator(`${rootSelector} .codeline-tray`);
      },
      get codelines() {
        return page.locator(`${rootSelector} li.codeline`);
      },
    },
    inputs: {
      get main() {
        return page.locator(`${rootSelector} > input.main`);
      },
      get log() {
        return page.locator(`${rootSelector} > input.log`);
      },
    },
    blanks: {
      get all() {
        return page.locator(`${rootSelector} input.parsons-blank`);
      },
      get missing() {
        return page.locator(`${rootSelector} input.parsons-blank-missing`);
      },
    },
    controls: {
      get all() {
        return page.locator(controlsSelector);
      },
      get copy() {
        return page.locator(`${controlsSelector} .widget-copy`);
      },
      get help() {
        return page.locator(`${controlsSelector} .widget-help`);
      },
    },
    text: {
      get pre() {
        return page.locator(`${rootSelector} .pre-text-wrapper`);
      },
      get post() {
        return page.locator(`${rootSelector} .post-text-wrapper`);
      },
    },
    aria: {
      get descriptor() {
        return page.locator(`#pl-faded-parsons-aria-descriptor-${uuid}`);
      },
      get details() {
        return page.locator(`#pl-faded-parsons-aria-details-${uuid}`);
      },
    },
  };
}
