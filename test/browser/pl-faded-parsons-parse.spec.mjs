import { expect, test } from "@playwright/test";

import { mountQuestion, parsons, parseQuestionFromPage } from "./support.mjs";


test.describe("pl-faded-parsons parse harness", () => {
  test("parses optional fades as blanks when the variant renders them", async ({ page }) => {
    const elementHtml = `<pl-faded-parsons answers-name="demo" file-name="student.py" language="python">
        <code-lines>result = __[value](hint)__ #pin(1)</code-lines>
      </pl-faded-parsons>`;

    await mountQuestion(page, elementHtml, {
      variant_seed: 0,
    });

    const blank = parsons(page).blanks.all.first();
    await blank.fill("answer");

    const parsed = await parseQuestionFromPage(page, elementHtml, {
      variant_seed: 0,
    });
    expect(parsed.submitted_answers.demo).toBe("    result = answer");
    expect(parsed.submitted_answers._files["student.py"]).toBeDefined();
    expect(parsed.format_errors).toEqual({});
  });

  test("parses optional fades as blanks when the variant renders them (reverse syntax)", async ({ page }) => {
    const elementHtml = `<pl-faded-parsons answers-name="demo" file-name="student.py" language="python">
        <code-lines>result = __(hint)[value]__ #pin(1)</code-lines>
      </pl-faded-parsons>`;

    await mountQuestion(page, elementHtml, {
      variant_seed: 0,
    });

    const blank = parsons(page).blanks.all.first();
    await blank.fill("answer");

    const parsed = await parseQuestionFromPage(page, elementHtml, {
      variant_seed: 0,
    });
    expect(parsed.submitted_answers.demo).toBe("    result = answer");
    expect(parsed.submitted_answers._files["student.py"]).toBeDefined();
    expect(parsed.format_errors).toEqual({});
  });

  test("parses optional fades as text when the variant omits them", async ({ page }) => {
    const elementHtml = `<pl-faded-parsons answers-name="demo" max-optional-fades="1" file-name="student.py" language="python">
        <code-lines>__[result]__ = __[value](hint)__ #pin</code-lines>
      </pl-faded-parsons>`;

    await mountQuestion(page, elementHtml);

    await parsons(page).blanks.all.first().fill("answer");

    const parsed = await parseQuestionFromPage(page, elementHtml);

    expect(parsed.submitted_answers.demo).toMatch(/result = answer|answer = value/);
  });

  test("parses optional fades as text when the variant omits them (reverse syntax)", async ({ page }) => {
    const elementHtml = `<pl-faded-parsons answers-name="demo" max-optional-fades="1" file-name="student.py" language="python">
        <code-lines>__[result]__ = __(hint)[value]__ #pin</code-lines>
      </pl-faded-parsons>`;

    await mountQuestion(page, elementHtml);

    await parsons(page).blanks.all.first().fill("answer");

    const parsed = await parseQuestionFromPage(page, elementHtml);

    expect(parsed.submitted_answers.demo).toMatch(/result = answer|answer = value/);
  });

  test("parses the manipulated widget DOM into submitted code", async ({ page }) => {
    const elementHtml = `<pl-faded-parsons answers-name="demo" file-name="student.py" language="python">
        <code-lines>result = __(value)__ #pin(1)</code-lines>
      </pl-faded-parsons>`;

    await mountQuestion(
      page,
      elementHtml,
    );

    const blank = parsons(page).blanks.all.first();
    await blank.fill("answer");

    const parsed = await parseQuestionFromPage(page, elementHtml);
    expect(parsed.submitted_answers.demo).toBe("    result = answer");
    expect(parsed.submitted_answers._files["student.py"]).toBeDefined();
    expect(parsed.format_errors).toEqual({});
  });

  test("parses c-style pinned lines with // comments", async ({ page }) => {
    const elementHtml = `<pl-faded-parsons answers-name="demo" file-name="student.js" language="javascript">
        <code-lines>result = __(value)__ //pin(1)</code-lines>
      </pl-faded-parsons>`;

    await mountQuestion(
      page,
      elementHtml,
    );

    const blank = parsons(page).blanks.all.first();
    await blank.fill("answer");

    const parsed = await parseQuestionFromPage(page, elementHtml);
    expect(parsed.submitted_answers.demo).toBe("    result = answer");
    expect(parsed.submitted_answers._files["student.js"]).toBeDefined();
    expect(parsed.format_errors).toEqual({});
  });

  test("preserves literal Song text in the rendered code block", async ({ page }) => {
    const elementHtml = `<pl-faded-parsons answers-name="song" language="python">
        <code-lines>
              return f"<Song> {super().desc()}"
        </code-lines>
    </pl-faded-parsons>`;

    await mountQuestion(page, elementHtml);

    expect(parsons(page).all.codelines).toHaveCount(1);
    const songLine = parsons(page).all.codelines.first();
    await expect(songLine).toContainText("<Song>", { ignoreCase: false});
    await expect(songLine).not.toContainText("<song>", { ignoreCase: false});
    await expect(songLine).not.toContainText("</song>", { ignoreCase: false});
  });

  test("preserves XML tags in submitted blanks during parse transport", async ({ page }) => {
    const elementHtml = `<pl-faded-parsons answers-name="demo" file-name="student.py" language="python">
        <code-lines>value = __(answer)__ #pin(1)</code-lines>
      </pl-faded-parsons>`;

    await mountQuestion(page, elementHtml);

    const blank = parsons(page).blanks.all.first();
    await blank.fill("<Song>");
    await expect(blank).toHaveValue("<Song>");

    const parsed = await parseQuestionFromPage(page, elementHtml);
    expect(parsed.submitted_answers.demo).toBe("    value = <Song>");
    expect(parsed.submitted_answers._files["student.py"]).toBeDefined();
    expect(parsed.format_errors).toEqual({});
  });

  test("returns a format error when a blank is left empty", async ({ page }) => {
    const elementHtml = `<pl-faded-parsons answers-name="demo" file-name="student.py" language="python">
        <code-lines>result = ___ #pin(1)</code-lines>
      </pl-faded-parsons>`;

    await mountQuestion(
      page,
      elementHtml,
    );

    const parsed = await parseQuestionFromPage(page, elementHtml);
    expect(parsed.format_errors.demo).toContain("incomplete blanks");
    expect(parsed.submitted_answers.demo).toBeUndefined();
  });
});
