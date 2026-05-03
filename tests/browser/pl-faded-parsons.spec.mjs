import { expect, test } from "@playwright/test";

import {
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

    const root = page.locator("#pl-faded-parsons-uuid-123");
    await expect(root).toHaveClass(/pl-faded-parsons-borderless/);
    await expect(page.locator("#starter-code-uuid-123")).toBeVisible();
    await expect(page.locator("#solution-uuid-123")).toBeVisible();
    await expect(page.locator("#widget-controls-uuid-123 .widget-help")).toHaveCount(1);
    await expect(page.locator("#widget-controls-uuid-123 .widget-help")).toHaveAttribute(
      "aria-label",
      "help text",
    );

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

    const blank = page.locator("input.parsons-blank");
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

    const line = page.locator("#ol-solution-uuid-123 li.codeline").first();
    await line.focus();
    await line.press("Tab");

    const stored = await parseStoredMain(page);
    expect(stored.solution[0].indent).toBe(1);
    await expect(line).toHaveAttribute("style", /--pl-faded-parsons-indent:\s*1/);
  });

  test("copies plaintext from the widget when the copy button is enabled", async ({ page }) => {
    await mountQuestion(
      page,
      `<pl-faded-parsons answers-name="demo" language="javascript" enable-copy-code="true">
        <code-lines>helper()
answer() #1given</code-lines>
      </pl-faded-parsons>`,
    );

    await page.locator("#widget-controls-uuid-123 .widget-copy").click();

    const clipboardWrites = await page.evaluate(() => window.__clipboardWrites);
    expect(clipboardWrites).toHaveLength(1);
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

    await expect(page.locator("#starter-code-uuid-123")).toHaveCount(0);
    await expect(page.locator("#solution-uuid-123")).toBeVisible();
    await expect(page.locator("#pl-faded-parsons-uuid-123")).not.toHaveClass(/pl-faded-parsons-borderless/);
    await expect(page.locator(".pre-text-wrapper")).toBeVisible();
    await expect(page.locator(".post-text-wrapper")).toBeVisible();
    await expect(page.locator("#pl-faded-parsons-uuid-123 > input.main")).toHaveCount(1);

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
