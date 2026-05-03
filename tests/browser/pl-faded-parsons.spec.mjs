import { expect, test } from "@playwright/test";

import {
  parsons,
  mountQuestion,
  parseStoredLog,
  parseStoredMain,
} from "./support.mjs";


test.describe("pl-faded-parsons browser behavior", () => {
  test("boots with the rendered trays and initial storage", async ({ page }) => {
    await mountQuestion(
      page,
      `<pl-faded-parsons answers-name="demo" language="javascript">
        <code-lines>helper()
answer() #1given</code-lines>
      </pl-faded-parsons>`,
    );

    const ui = parsons(page);
    await expect(ui.root).toHaveClass(/pl-faded-parsons-borderless/);
    await expect(ui.trays.starter).toBeVisible();
    await expect(ui.trays.solution).toBeVisible();
    await expect(ui.controls.help).toHaveCount(1);
    await expect(ui.controls.help).toHaveAttribute(
      "aria-label",
      "help text",
    );
    await expect(ui.codelines.all).toHaveCount(2);

    const stored = await parseStoredMain(page);
    expect(stored.starter).toHaveLength(1);
    expect(stored.solution).toHaveLength(1);
    expect(stored.starter[0].codeSnippets.join("")).toContain("helper()");
    expect(stored.solution[0].codeSnippets.join("")).toContain("answer()");
  });

  test("updates the hidden submission state when a blank changes", async ({ page }) => {
    await mountQuestion(
      page,
      `<pl-faded-parsons answers-name="demo" language="python">
        <code-lines>value = !BLANK #1given</code-lines>
      </pl-faded-parsons>`,
    );

    const blank = parsons(page).blanks.all;
    await expect(blank).toHaveAttribute("aria-invalid", "true");
    await blank.click();
    await blank.fill("answer");

    const stored = await parseStoredMain(page);
    expect(stored.solution[0].blankValues).toEqual(["answer"]);
    await expect(blank).not.toHaveAttribute("aria-invalid", "true");
    await expect(blank).not.toHaveClass(/parsons-blank-missing/);
  });

  test("reindents a focused line with the keyboard and stores the new indent", async ({ page }) => {
    await mountQuestion(
      page,
      `<pl-faded-parsons answers-name="demo" format="one-tray" language="javascript">
        <code-lines>answer()</code-lines>
      </pl-faded-parsons>`,
    );

    const line = parsons(page).codelines.solution.first();
    await line.focus();
    await line.press("Tab");

    const stored = await parseStoredMain(page);
    expect(stored.solution[0].indent).toBe(1);
    await expect(line).toHaveAttribute("style", /--pl-faded-parsons-indent:\s*1/);
  });

  test("moves a starter line into the solution tray with Option+ArrowRight", async ({ page }) => {
    await mountQuestion(
      page,
      `<pl-faded-parsons answers-name="demo" language="javascript">
        <code-lines>helper()
answer() #1given</code-lines>
      </pl-faded-parsons>`,
    );

    const starterLine = parsons(page).codelines.starter.first();
    await starterLine.focus();
    await starterLine.press("Alt+ArrowRight");

    await expect.poll(() => parseStoredMain(page)).toMatchObject({
      starter: [],
      solution: [
        { codeSnippets: ["helper()"], indent: 0 },
        { codeSnippets: ["answer()"], indent: 1 },
      ],
    });
    await expect(parsons(page).codelines.starter).toHaveCount(0);
    await expect(parsons(page).codelines.solution).toHaveCount(2);
    await expect(parsons(page).codelines.solution.first()).toContainText("helper()");
  });

  test("moves a solution line back into the starter tray with Option+ArrowLeft", async ({ page }) => {
    await mountQuestion(
      page,
      `<pl-faded-parsons answers-name="demo" language="javascript">
        <code-lines>helper()
answer() #1given</code-lines>
      </pl-faded-parsons>`,
    );

    const starterLine = parsons(page).codelines.starter.first();
    await starterLine.focus();
    await starterLine.press("Alt+ArrowRight");

    const movedLine = parsons(page).codelines.solution.first();
    await movedLine.focus();
    await movedLine.press("Alt+ArrowLeft");

    await expect.poll(() => parseStoredMain(page)).toMatchObject({
      starter: [
        { codeSnippets: ["helper()"], indent: 0 },
      ],
      solution: [
        { codeSnippets: ["answer()"], indent: 1 },
      ],
    });
    await expect(parsons(page).codelines.starter).toHaveCount(1);
    await expect(parsons(page).codelines.solution).toHaveCount(1);
    await expect(parsons(page).codelines.starter.first()).toContainText("helper()");
  });

  test("copies plaintext from the widget when the copy button is enabled", async ({ page }) => {
    await mountQuestion(
      page,
      `<pl-faded-parsons answers-name="demo" language="javascript" enable-copy-code="true">
        <code-lines>helper()
answer() #1given</code-lines>
      </pl-faded-parsons>`,
    );

    await parsons(page).controls.copy.click();

    await expect.poll(() => page.evaluate(() => window.__clipboardWrites.length)).toBe(1);
    const clipboardWrites = await page.evaluate(() => window.__clipboardWrites);
    expect(clipboardWrites[0]).toContain("// helper()");
    expect(clipboardWrites[0]).toContain("answer()");
  });

  test("renders the one-tray variant without a starter tray and without the borderless class", async ({ page }) => {
    await mountQuestion(
      page,
      `<pl-faded-parsons answers-name="demo" format="one-tray" language="python">
        <pre-text>before()</pre-text>
        <code-lines visual-indent="2">kept()
answer() #1given</code-lines>
        <post-text>after()</post-text>
      </pl-faded-parsons>`,
    );

    const ui = parsons(page);
    await expect(ui.trays.starter).toHaveCount(0);
    await expect(ui.trays.solution).toBeVisible();
    await expect(ui.root).not.toHaveClass(/pl-faded-parsons-borderless/);
    await expect(ui.text.pre).toBeVisible();
    await expect(ui.text.post).toBeVisible();
    await expect(ui.inputs.main).toHaveCount(1);

    const stored = await parseStoredMain(page);
    expect(stored.starter).toEqual([]);
    expect(stored.solution).toHaveLength(2);
  });

  test("records an opening log entry when logging is enabled", async ({ page }) => {
    await mountQuestion(
      page,
      `<pl-faded-parsons answers-name="demo" language="python" log="true">
        <code-lines>helper()
answer() #1given</code-lines>
      </pl-faded-parsons>`,
    );

    const log = await parseStoredLog(page);
    expect(log).toHaveLength(1);
    expect(log[0].tag).toBe("problemOpened");
  });
});
