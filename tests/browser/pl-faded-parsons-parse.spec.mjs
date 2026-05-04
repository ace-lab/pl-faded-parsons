import { expect, test } from "@playwright/test";

import { mountQuestion, parsons, parseQuestionFromPage } from "./support.mjs";


test.describe("pl-faded-parsons parse harness", () => {
  test("parses the manipulated widget DOM into submitted code", async ({ page }) => {
    const elementHtml = `<pl-faded-parsons answers-name="demo" file-name="student.py" language="python">
        <code-lines>result = !BLANK #blank value #1given</code-lines>
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

  test("returns a format error when a blank is left empty", async ({ page }) => {
    const elementHtml = `<pl-faded-parsons answers-name="demo" file-name="student.py" language="python">
        <code-lines>result = !BLANK #1given</code-lines>
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
