import { expect, test } from "@playwright/test";

import {
  parsons,
  mountQuestion,
  parseStoredLog,
  parseStoredMain,
} from "./support.mjs";

// if you can avoid writing in this file, you probably should
// these tests are orders of magnitude slower to run than in the python above
// this exists merely for e2e behavioral testing through mouse/key interactions

test.describe("pl-faded-parsons browser behavior", () => {
  test("boots with the rendered trays and initial storage", async ({ page }) => {
    await mountQuestion(
      page,
      `<pl-faded-parsons answers-name="demo" language="javascript">
        <code-lines>helper()
answer() #pin</code-lines>
      </pl-faded-parsons>`,
    );

    const ui = parsons(page);
    await expect(ui.root).toHaveClass(/pl-faded-parsons-borderless/);
    await expect(ui.starter.tray).toBeVisible();
    await expect(ui.solution.tray).toBeVisible();
    await expect(ui.controls.help).toHaveCount(1);
    await expect(ui.controls.help).toHaveAttribute(
      "aria-label",
      "help text",
    );
    await expect(ui.all.codelines).toHaveCount(2);

    const stored = await parseStoredMain(page);
    expect(stored.starter).toHaveLength(1);
    expect(stored.solution).toHaveLength(1);
    expect(stored.starter[0].codeSnippets.join("")).toContain("helper()");
    expect(stored.solution[0].codeSnippets.join("")).toContain("answer()");
    expect(stored.solution[0].indent).toBe(0);
  });

  test("bottom layout places the unused label in the lower-left corner", async ({ page }) => {
    await mountQuestion(
      page,
      `<pl-faded-parsons answers-name="demo" format="bottom" language="javascript">
        <code-lines>helper()
answer() #pin(1)</code-lines>
      </pl-faded-parsons>`,
    );

    await expect(parsons(page).root).toHaveClass(/pl-faded-parsons-bottom-layout/);
    const unusedLabel = parsons(page).starter.tray.locator(".fpp-tray-corner-label-starter");
    const [labelBox, trayBox] = await Promise.all([
      unusedLabel.boundingBox(),
      parsons(page).starter.tray.boundingBox(),
    ]);
    expect(labelBox).not.toBeNull();
    expect(trayBox).not.toBeNull();
    expect(labelBox.x).toBeLessThan(trayBox.x + trayBox.width / 2);
  });

  test("updates the hidden submission state when a blank changes", async ({ page }) => {
    await mountQuestion(
      page,
      `<pl-faded-parsons answers-name="demo" language="python">
        <code-lines>value = __(answer)__ #pin(1)</code-lines>
      </pl-faded-parsons>`,
    );

    const blank = parsons(page).blanks.all;
    const initialStored = await parseStoredMain(page);
    expect(initialStored.solution[0].blankValues).toEqual([""]);
    expect(initialStored.solution[0].blankPlaceholders).toEqual(["answer"]);
    await expect(blank).toHaveAttribute("aria-invalid", "true");
    await expect(blank).toHaveAttribute("placeholder", "answer");
    await expect(blank).toHaveValue("");
    await blank.click();
    await blank.fill("answer");

    const stored = await parseStoredMain(page);
    expect(stored.solution[0].blankValues).toEqual(["answer"]);
    expect(stored.solution[0].blankPlaceholders).toEqual(["answer"]);
    await expect(blank).not.toHaveAttribute("aria-invalid", "true");
    await expect(blank).not.toHaveClass(/parsons-blank-missing/);
  });

  test.describe("Tab motions", () => {
    test("reindents a focused line with the keyboard and stores the new indent", async ({ page }) => {
      await mountQuestion(
        page,
        `<pl-faded-parsons answers-name="demo" format="one-tray" language="javascript">
          <code-lines>answer()</code-lines>
        </pl-faded-parsons>`,
      );

      const line = parsons(page).solution.codelines.first();
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
answer() #pin(1)</code-lines>
        </pl-faded-parsons>`,
      );

      const starterLine = parsons(page).starter.codelines.first();
      await starterLine.focus();
      await starterLine.press("Alt+ArrowRight");

      await expect.poll(() => parseStoredMain(page)).toMatchObject({
        starter: [],
        solution: [
          { codeSnippets: ["helper()"], indent: 0 },
          { codeSnippets: ["answer()"], indent: 1 },
        ],
      });
      await expect(parsons(page).starter.codelines).toHaveCount(0);
      await expect(parsons(page).solution.codelines).toHaveCount(2);
      await expect(parsons(page).solution.codelines.first()).toContainText("helper()");
    });

    test("Tab moves a starter line into the solution tray", async ({ page }) => {
      await mountQuestion(
        page,
        `<pl-faded-parsons answers-name="demo" language="javascript">
          <code-lines>helper()
answer() #pin(1)</code-lines>
        </pl-faded-parsons>`,
      );

      const starterLine = parsons(page).starter.codelines.first();
      await starterLine.focus();
      await starterLine.press("Tab");

      await expect.poll(() => parseStoredMain(page)).toMatchObject({
        starter: [],
        solution: [
          { codeSnippets: ["helper()"], indent: 0 },
          { codeSnippets: ["answer()"], indent: 1 },
        ],
      });
      await expect(parsons(page).starter.codelines).toHaveCount(0);
      await expect(parsons(page).solution.codelines).toHaveCount(2);
      await expect(parsons(page).solution.codelines.first()).toContainText("helper()");
    });

    test("Shift+Tab does not send a solution line back into the starter tray", async ({ page }) => {
      await mountQuestion(
        page,
        `<pl-faded-parsons answers-name="demo" language="javascript">
          <code-lines>helper()
answer() #pin(1)</code-lines>
        </pl-faded-parsons>`,
      );

      const starterLine = parsons(page).starter.codelines.first();
      await starterLine.focus();
      await starterLine.press("Tab");

      const movedLine = parsons(page).solution.codelines.first();
      await movedLine.press("Shift+Tab");

      await expect.poll(() => parseStoredMain(page)).toMatchObject({
        starter: [],
        solution: [
          { codeSnippets: ["helper()"], indent: 0 },
          { codeSnippets: ["answer()"], indent: 1 },
        ],
      });
      await expect(parsons(page).starter.codelines).toHaveCount(0);
      await expect(parsons(page).solution.codelines).toHaveCount(2);
      await expect(parsons(page).solution.codelines.first()).toContainText("helper()");
    });

    test("Tab caps out at the configured max indent level", async ({ page }) => {
      await mountQuestion(
        page,
        `<pl-faded-parsons answers-name="demo" format="one-tray" language="javascript" max-indent-level="1">
          <code-lines>answer()</code-lines>
        </pl-faded-parsons>`,
      );

      const line = parsons(page).solution.codelines.first();
      await line.focus();
      await line.press("Tab");
      await line.press("Tab");

      const stored = await parseStoredMain(page);
      expect(stored.solution[0].indent).toBe(1);
      await expect(line).toHaveAttribute("style", /--pl-faded-parsons-indent:\s*1/);
    });

    test("Shift+Tab bottoms out at zero indent", async ({ page }) => {
      await mountQuestion(
        page,
        `<pl-faded-parsons answers-name="demo" format="one-tray" language="javascript">
          <code-lines>answer()</code-lines>
        </pl-faded-parsons>`,
      );

      const line = parsons(page).solution.codelines.first();
      await line.focus();
      await line.press("Shift+Tab");

      const stored = await parseStoredMain(page);
      expect(stored.solution[0].indent).toBe(0);
      await expect(line).toHaveAttribute("style", /--pl-faded-parsons-indent:\s*0/);
    });

    test("Tab stays inside the codeline in one-tray mode", async ({ page }) => {
      await mountQuestion(
        page,
        `<pl-faded-parsons answers-name="demo" format="one-tray" language="javascript">
          <code-lines>answer()</code-lines>
        </pl-faded-parsons>`,
      );

      const line = parsons(page).solution.codelines.first();
      await line.focus();
      await line.press("Tab");

      const stored = await parseStoredMain(page);
      expect(stored.solution[0].indent).toBe(1);
      await expect(line).toBeFocused();
    });

    test("moves a solution line back into the starter tray with Option+ArrowLeft", async ({ page }) => {
      await mountQuestion(
        page,
        `<pl-faded-parsons answers-name="demo" language="javascript">
          <code-lines>helper()
answer() #pin(1)</code-lines>
        </pl-faded-parsons>`,
      );

      const starterLine = parsons(page).starter.codelines.first();
      await starterLine.focus();
      await starterLine.press("Alt+ArrowRight");

      const movedLine = parsons(page).solution.codelines.first();
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
      await expect(parsons(page).starter.codelines).toHaveCount(1);
      await expect(parsons(page).solution.codelines).toHaveCount(1);
      await expect(parsons(page).starter.codelines.first()).toContainText("helper()");
    });

    test("bottom layout uses ArrowDown and ArrowUp to cross trays at tray edges", async ({ page }) => {
      await mountQuestion(
        page,
        `<pl-faded-parsons answers-name="demo" format="bottom" language="javascript">
          <code-lines>helper()
answer() #pin(1)</code-lines>
        </pl-faded-parsons>`,
      );

      const starterLine = parsons(page).starter.codelines.first();
      await starterLine.focus();
      await starterLine.press("ArrowDown");
      await expect(parsons(page).solution.codelines.first()).toBeFocused();

      const solutionLine = parsons(page).solution.codelines.first();
      await solutionLine.press("ArrowUp");
      await expect(parsons(page).starter.codelines.first()).toBeFocused();
    });

    test("bottom layout uses Option+ArrowDown and Option+ArrowUp to move lines across trays at tray edges", async ({ page }) => {
      await mountQuestion(
        page,
        `<pl-faded-parsons answers-name="demo" format="bottom" language="javascript">
          <code-lines>helper()
answer() #pin(1)</code-lines>
        </pl-faded-parsons>`,
      );

      const starterLine = parsons(page).starter.codelines.first();
      await starterLine.focus();
      await starterLine.press("Alt+ArrowDown");

      await expect.poll(() => parseStoredMain(page)).toMatchObject({
        starter: [],
        solution: [
          { codeSnippets: ["helper()"], indent: 0 },
          { codeSnippets: ["answer()"], indent: 1 },
        ],
      });

      const movedLine = parsons(page).solution.codelines.first();
      await movedLine.focus();
      await movedLine.press("Alt+ArrowUp");

      await expect.poll(() => parseStoredMain(page)).toMatchObject({
        starter: [
          { codeSnippets: ["helper()"], indent: 0 },
        ],
        solution: [
          { codeSnippets: ["answer()"], indent: 1 },
        ],
      });
    });

    test("bottom layout ignores left and right tray navigation keys", async ({ page }) => {
      await mountQuestion(
        page,
        `<pl-faded-parsons answers-name="demo" format="bottom" language="javascript">
          <code-lines>helper()
answer() #pin(1)</code-lines>
        </pl-faded-parsons>`,
      );

      const starterLine = parsons(page).starter.codelines.first();
      await starterLine.focus();
      await starterLine.press("ArrowRight");
      await expect(starterLine).toBeFocused();
      await expect.poll(() => parseStoredMain(page)).toMatchObject({
        starter: [
          { codeSnippets: ["helper()"], indent: 0 },
        ],
        solution: [
          { codeSnippets: ["answer()"], indent: 1 },
        ],
      });

      await starterLine.press("Alt+ArrowRight");
      await expect(starterLine).toBeFocused();
      await expect.poll(() => parseStoredMain(page)).toMatchObject({
        starter: [
          { codeSnippets: ["helper()"], indent: 0 },
        ],
        solution: [
          { codeSnippets: ["answer()"], indent: 1 },
        ],
      });
    });
  });

  test("copies plaintext from the widget when the copy button is enabled", async ({ page }) => {
    await mountQuestion(
      page,
      `<pl-faded-parsons answers-name="demo" language="javascript" enable-copy-code="true">
        <code-lines>helper()
answer() #pin(1)</code-lines>
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
answer() #pin(1)</code-lines>
        <post-text>after()</post-text>
      </pl-faded-parsons>`,
    );

    const ui = parsons(page);
    await expect(ui.starter.codelines).toHaveCount(0);
    await expect(ui.solution.tray).toBeVisible();
    await expect(ui.root).not.toHaveClass(/pl-faded-parsons-borderless/);
    await expect(ui.text.pre).toBeVisible();
    await expect(ui.text.post).toBeVisible();
    await expect(ui.inputs.main).toHaveCount(1);

    const stored = await parseStoredMain(page);
    expect(stored.starter).toEqual([]);
    expect(stored.solution).toHaveLength(2);
  });

  test.describe("Logging", () => {
    test("records an opening log entry when logging is enabled", async ({ page }) => {
      await mountQuestion(
        page,
        `<pl-faded-parsons answers-name="demo" language="python" log="true">
          <code-lines>helper()
answer() #pin(1)</code-lines>
        </pl-faded-parsons>`,
      );

      const log = await parseStoredLog(page);
      expect(log).toHaveLength(1);
      expect(log[0].tag).toBe("problemOpened");
    });

    test("records a log entry when a line moves into the solution tray", async ({ page }) => {
      await mountQuestion(
        page,
        `<pl-faded-parsons answers-name="demo" language="javascript" log="true">
          <code-lines>helper()
answer() #pin(1)</code-lines>
        </pl-faded-parsons>`,
      );

      await parsons(page).starter.codelines.first().dragTo(parsons(page).solution.tray);

      const log = await parseStoredLog(page);
      expect(log).toHaveLength(2);
      expect(log[0].tag).toBe("problemOpened");
      // expect(log[1].tag).toBe("addOutput");
      expect(log[1].data.indent).toBe(0);
      expect(log[1].data.segments.codeSnippets.join("")).toContain("helper()");
    });

    test("records a log entry when a blank is edited", async ({ page }) => {
      await mountQuestion(
        page,
        `<pl-faded-parsons answers-name="demo" language="python" log="true">
          <code-lines>value = ___ #pin(1)</code-lines>
        </pl-faded-parsons>`,
      );

      const blank = parsons(page).blanks.all.first();
      await blank.click();
      await blank.fill("answer");

      const log = await parseStoredLog(page);
      expect(log).toHaveLength(2);
      expect(log[0].tag).toBe("problemOpened");
      expect(log[1].tag).toBe("editBlank");
      expect(log[1].data.value).toBe("answer");
      expect(log[1].data.id).toBe("1.0.0");
    });
  });
});
