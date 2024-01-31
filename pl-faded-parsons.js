/** expects a config with a `uuid` and fields that align with this schema:
 * ```
 *  ...
 *  <div#{{config.main}}.fpp-global-defs>
 *    <!-- inputs in the template that will save
 *         the student's progress between reloads
 *    -->
 *    <input#{{config.solutionOrderStorage}}
 *    <input#{{config.starterOrderStorage}}
 *   ...
 *   ( <!-- A starter tray is optional -->
 *      <div#{{config.starter}}.codeline-tray>
 *         <ul#{{config.starterList}}.codeline-list>
 *           <li.codeline> ... <input.parsons-blank>* ... </li>*
 *         </ul>
 *       </div>
 *   )?
 *    ...
 *    <div#{{config.solution}}.codeline-tray>
 *       <ul#{{config.solutionList}}.codeline-list>
 *         <li.codeline> ... <input.parsons-blank>* ... </li>*
 *       </ul>
 *    </div>
 *     ...
 *    <div#{{config.toolbar}>
 *       ...
 *       <div.fpp-help data-toggle="popover"></div>
 *       <div.fpp-copy></div>
 *       <div.fpp-dark></div>
 *       ...
 *    </div>
 *     ...
 *  </div>
 * ```
 */
class ParsonsWidget {
  /** Creates a new widget instance. See class docs for info on `config`. */
  constructor(config) {
    this.config = jQuery.extend(
      {
        xIndent: 4,
        canIndent: true,
        prettyPrint: true,
        onSortableUpdate: (_event, _ui) => {},
        onBlankUpdate: (_event, _input) => {},
        lang: "en",
      },
      config,
    );

    const requiredFields =
      "uuid solution solutionList main toolbar starterOrderStorage solutionOrderStorage solutionSubmissionStorage";
    const missing = requiredFields
      .split(" ")
      .filter((f) => this.config[f] == null)
      .join(", ");
    if (missing)
      throw new Error(
        `ParsonsWidget config requires field(s) ${missing} to be non-null`,
      );

    if (this.config.prettyPrint) {
      (
        window.prettyPrint ||
        function () {
          console.error("prettify bindings missing!");
        }
      )();
    }

    $("form.question-form").submit(() => this.storeStudentProgress());

    $(this.config.toolbar)
      .find(`.widget-help`)
      .popover({
        content: () =>
          [
            "Use the mouse or keyboard to rearrange and reindent the lines of code and then fill in the blanks.",
            "Arrow Keys: Select",
            "Alt/Opt+Arrow Keys: Reorder",
            "(Shift+)Tab: Down/Up Indent",
            "(Shift+)Enter: Enter Prev/Next Blank",
          ].join("<br>"),
      });

    $(this.config.toolbar)
      .find(`.widget-copy`)
      .on({
        click: () => {
          if (navigator.clipboard) {
            navigator.clipboard.writeText(this.asPlaintext()).catch((err) => {
              console.error("Unable to copy text to clipboard", err);
              alert("Your browser blocked clipboard write access :(");
            });
          } else {
            alert("Your browser does not yet support this :(");
          }
        },
      });

    $(this.config.toolbar)
      .find(".widget-dark")
      .on({ click: () => ParsonsGlobal.toggleDarkmode() });

    const widget = this;
    const solutionTray = $(widget.config.solutionList).sortable({
      start: function (event, ui) {
        $(ui.item).focus().addClass("codeline-in-motion");
        widget.clearFeedback();
      },
      stop: function (event, ui) {
        $(ui.item).blur().removeClass("codeline-in-motion");
        if ($(event.target)[0] != ui.item.parent()[0]) {
          return;
        }

        widget.updateIndent(
          widget.calculateCodeIndent(
            ui.position.left - ui.item.parent().position().left,
            ui.item[0],
          ),
          ui.item[0],
        );

        widget.addLogEntry({ type: "moveOutput", target: ui.item[0].id }, true);
      },
      receive: function (_event, ui) {
        widget.updateIndent(
          widget.calculateCodeIndent(
            ui.position.left - ui.item.parent().position().left,
            ui.item[0],
          ),
          ui.item[0],
        );

        widget.addLogEntry({ type: "addOutput", target: ui.item[0].id }, true);
      },
      update: (e, ui) => widget.config.onSortableUpdate(e, ui),
      grid: widget.config.canIndent ? [widget.config.xIndent, 1] : false,
    });
    solutionTray.addClass("output");

    if (widget.config.starter) {
      const starterTray = $(widget.config.starterList).sortable({
        connectWith: solutionTray,
        start: function (_event, ui) {
          $(ui.item).focus().addClass("codeline-in-motion");
          widget.clearFeedback();
        },
        receive: function (_event, ui) {
          widget.updateIndent(0, ui.item[0].id);
          widget.addLogEntry(
            { type: "removeOutput", target: ui.item[0].id },
            true,
          );
        },
        stop: function (event, ui) {
          $(ui.item).blur().removeClass("codeline-in-motion");
          if ($(event.target)[0] != ui.item.parent()[0]) {
            // line moved to output and logged there
            return;
          }
          widget.addLogEntry(
            { type: "moveInput", target: ui.item[0].id },
            true,
          );
        },
      });
      solutionTray.sortable("option", "connectWith", starterTray);
    }

    widget.redrawTabStops();

    $(widget.config.main)
      .find("li.codeline")
      .each(function (_, codeline) {
        // unstable idx because lines shift!
        widget.updateAriaLabel(codeline, false);

        /// definitions for arrow key handling /////////////////////////////
        const handleVerticalArrowKeys = (e) => {
          const children = $(codeline.parentElement).children();
          const index = children.index(codeline);
          const middleChild = 0 < index && index < children.length - 1;
          if (e.key.endsWith("Up")) {
            if (e.ctrlKey || e.metaKey) {
              children.first().focus();
            } else if (middleChild || index == children.length - 1) {
              e.preventDefault();
              const child = children.eq(index - 1);
              if (e.altKey) {
                child.insertAfter(codeline);
              } else {
                child.focus();
              }
            }
            return true;
          }
          if (e.key.endsWith("Down")) {
            if (e.ctrlKey || e.metaKey) {
              children.last().focus();
            } else if (middleChild || index == 0) {
              e.preventDefault();
              const child = children.eq(index + 1);
              if (e.altKey) {
                child.insertBefore(codeline);
              } else {
                child.focus();
              }
            }
            return true;
          }
          return false;
        };
        const navigateBetweenTrays = (moveCodelineNotCursor, rightward) => {
          const codeboxes = $(widget.config.main).find("div.codeline-tray");
          if (codeboxes.length < 2) return;
          const topPx = codeline.getBoundingClientRect().top;
          const codeboxIdx = codeboxes
            .toArray()
            .findIndex((c) => $(c).has(codeline).length);
          const k =
            (codeboxIdx + (rightward ? +1 : codeboxes.length - 1)) %
            codeboxes.length;
          const newTray = codeboxes.eq(k).find("ul.codeline-list").first();
          const parallelTarget = newTray
            .children()
            .filter((_, e) => e.getBoundingClientRect().bottom > topPx)
            .first();
          if (moveCodelineNotCursor) {
            if (parallelTarget.length) {
              $(codeline).insertBefore(parallelTarget);
            } else {
              $(newTray).append(codeline);
            }
            $(codeline).focus();
          } else {
            const newFocus = parallelTarget.length
              ? parallelTarget
              : newTray.children().last();
            newFocus.focus();
          }
        };

        /// setup callbacks on each codeline and its blanks ///////////////
        $(codeline).on({
          focus: function () {
            widget.updateAriaLabel(codeline);
            $(codeline).addClass("codeline-highlight");
          },
          blur: function () {
            widget.updateAriaLabel(codeline, false);
            $(codeline).removeClass("codeline-highlight");
          },
          click: function () {
            $(codeline).focus();
          },
          keyup: function (e) {
            if (!e.altKey) {
              $(codeline).removeClass("codeline-in-motion");
            }
          },
          keydown: function (e) {
            widget.updateAriaLabel(codeline);
            if (e.altKey) {
              $(codeline).addClass("codeline-in-motion");
            }

            if (!$(codeline).is(":focus")) return;
            // Tab/Shift+Tab to Indent/Dedent,
            // or Tab out of Starter Tray into Codeline
            if (e.key === "Tab") {
              e.preventDefault();
              const inTheStarterTray = $(widget.config.starter).has(
                codeline,
              ).length;
              if (inTheStarterTray) {
                navigateBetweenTrays(true, true);
              } else {
                const delta = e.shiftKey ? -1 : +1;
                widget.updateIndent(delta, codeline, false);
              }
              return;
            }
            // (Alt/Option)+Arrow to Reorder Lines, Arrow to Navigate
            if (e.key.startsWith("Arrow")) {
              if (!handleVerticalArrowKeys(e)) {
                e.preventDefault();
                navigateBetweenTrays(e.altKey, e.key.endsWith("Right"));
              }
              return;
            }
            // Enter to refocus on the blanks
            if (e.key === "Enter") {
              e.preventDefault();
              $(codeline).children("input").first().focus();
              return;
            }
            // Escape removes focus
            if (e.key === "Escape") {
              e.preventDefault();
              $(codeline).blur();
              return;
            }
          },
        });

        /// setup callbacks for the codeline's blanks //////////
        const inputs = $(codeline).find("input.parsons-blank");
        const n = inputs.length;
        inputs.each((_, input) => widget.autoSizeInput(input));
        inputs.each(
          (
            i,
            input, // note: because blanks are static, i is always the correct index into inputs.
          ) =>
            $(input).on({
              focus: () => $(codeline).addClass("codeline-highlight"),
              blur: () => $(codeline).removeClass("codeline-highlight"),
              click: (e) => {
                $(input).focus();
                e.stopPropagation();
              },
              input: (e) => {
                widget.autoSizeInput(input);
                widget.config.onBlankUpdate(e, input);
              },
              keydown: (e) => {
                // Tab/Shift+Tab to Indent/Dedent if on the first/last blank of line,
                // otherwise advance/retreat blanks on the line
                if (e.key === "Tab") {
                  const [boundary, delta] = e.shiftKey ? [0, -1] : [n - 1, +1];
                  if (
                    ParsonsGlobal.uiConfig.alwaysIndentOnTab ||
                    i == boundary
                  ) {
                    e.preventDefault();
                    widget.updateIndent(delta, codeline, false);
                  }
                  return;
                }
                // (Alt/Option)+Arrow to Reorder Lines
                // Arrow Up/Down to Navigate Lines
                // Arrow Right/Left to move cursor (including between input boxes)
                if (e.key.startsWith("Arrow")) {
                  if (!handleVerticalArrowKeys(e)) {
                    const cursorPosition = input.selectionStart;
                    if (input.selectionEnd == cursorPosition) {
                      if (
                        e.key.endsWith("Left") &&
                        cursorPosition == 0 &&
                        i != 0
                      ) {
                        e.preventDefault();
                        inputs
                          .eq(i - 1)
                          .focus()
                          .each((_j, inp) => {
                            inp.setSelectionRange(
                              inp.value.length,
                              inp.value.length,
                            );
                          });
                      }
                      if (
                        e.key.endsWith("Right") &&
                        cursorPosition == input.value.length &&
                        i != n - 1
                      ) {
                        e.preventDefault();
                        inputs
                          .eq(i + 1)
                          .focus()
                          .each((_j, inp) => {
                            inp.setSelectionRange(0, 0);
                          });
                      }
                    }
                  }
                  return;
                }
                // Escape to loose focus on the blank
                if (e.key === "Escape") {
                  $(codeline).focus();
                  e.stopPropagation();
                  return;
                }
                // Enter/Shift+Enter to advance/retreat blanks
                if (e.key === "Enter") {
                  e.preventDefault();
                  const delta = e.shiftKey ? -1 : +1;
                  const allInputs = $(codeline.parentElement).find("input");
                  const m = allInputs.length;
                  const nextIndex = (allInputs.index(input) + m + delta) % m;
                  allInputs.eq(nextIndex).focus();
                  return;
                }
              },
            }),
        );
      });
  }
  getCodelineIndent(elem) {
    let code_indent = NaN;

    if (elem.style !== null) {
      let raw_indent = parseInt(elem.style.marginLeft, 10);
      code_indent = raw_indent / this.config.xIndent;
    }

    return isNaN(code_indent) ? 0 : code_indent;
  }
  getCodelineSegments(codelineElem) {
    let elemClone = $(codelineElem).clone();
    let blankValues = [];
    elemClone.find("input").each(function (_, inp) {
      blankValues.push(inp.value);
      inp.replaceWith("!BLANK");
    });
    // this schema is used in pl-faded-parsons.py `read_lines`!
    return {
      givenSegments: elemClone.text().split("!BLANK"),
      blankValues: blankValues,
    };
  }
  codelineSummary(line, idx) {
    // this schema is used in pl-faded-parsons.py `read_lines`!
    return {
      content: this.getCodelineText(line),
      indent: this.getCodelineIndent(line),
      segments: this.getCodelineSegments(line),
      index: idx,
    };
  }
  autoSizeInput(el) {
    $(el).width(el.value.length.toString() + "ch");
  }
  getSourceLines() {
    return $(this.config.starterList).children().toArray();
  }
  getSolutionLines() {
    return $(this.config.solutionList).children().toArray();
  }
  calculateCodeIndent(dist_in_px, elem) {
    let dist = dist_in_px / ParsonsGlobal.charWidthInPx;
    let old_code_indent = this.getCodelineIndent(elem);
    let new_code_indent =
      old_code_indent + Math.floor(dist / this.config.xIndent);
    return Math.max(0, new_code_indent);
  }
  getSolutionCode() {
    const solution_lines = this.getSolutionLines();

    let solutionCode = "";
    let codeMetadata = "";
    let blankText = "";
    let originalLine = "";
    for (const line of solution_lines) {
      const lineClone = $(line).clone();

      blankText = "";
      lineClone.find("input").each(function (_, inp) {
        inp.replaceWith("!BLANK");
        blankText += " #blank" + inp.value;
      });
      lineClone[0].innerText = lineClone[0].innerText.trimRight();
      const lineText = this.getCodelineText(line);

      if (lineClone[0].innerText != lineText) {
        originalLine = " #!ORIGINAL" + lineClone[0].innerText + blankText;
      } else {
        originalLine = lineClone[0].innerText + blankText;
      }

      solutionCode += lineText + "\n";
      codeMetadata += originalLine + "\n";
    }

    return { solution: solutionCode, metadata: codeMetadata };
  }
  /** Reads a codeline element and interpolates the blanks with their value */
  getCodelineText(codeline) {
    let elemClone = $(codeline).clone();
    elemClone.find("input").each(function (_, inp) {
      inp.replaceWith(inp.value);
    });
    elemClone[0].innerText = elemClone[0].innerText.trimRight();

    const spaceCount = this.config.xIndent * this.getCodelineIndent(codeline);
    return " ".repeat(spaceCount) + elemClone[0].innerText;
  }
  /** Returns all the codeline in the widget as formatted code plaintext */
  asPlaintext() {
    const toText = (lines) =>
      lines.map(
        (line) =>
          " ".repeat(this.config.xIndent * this.getCodelineIndent(line)) +
          this.getCodelineSegments(line).givenSegments.join("BLANK"),
      );
    const lang = ($(this.config.main).attr("language") || "").toLowerCase();
    const commentPrefix = [
      "java",
      "c",
      "c++",
      "c#",
      "js",
      "javascript",
      "ts",
      "typescript",
    ].includes(lang)
      ? "# "
      : "// ";
    const starters = toText(this.getSourceLines()).map(
      (s) => commentPrefix + s,
    );
    const sols = toText(this.getSolutionLines());
    return [...starters, ...sols].join("\n");
  }
  /** Sets the indent of the element in language terms (not pxs),
   *  if not absolute, then it will update relative to the current indent.
   */
  updateIndent(new_code_indent, elem, absolute = true) {
    if (!this.config.canIndent) return;

    let old_code_indent = this.getCodelineIndent(elem);
    if (!absolute) new_code_indent += old_code_indent;

    if (old_code_indent != new_code_indent && new_code_indent >= 0) {
      this.config.onSortableUpdate(
        {
          type: "reindent",
          content: this.getCodelineText(elem),
          old: old_code_indent,
          new: new_code_indent,
        },
        this.getSolutionLines(),
      );

      $(elem).css("margin-left", this.config.xIndent * new_code_indent + "ch");

      this.redrawTabStops();
    }
    this.updateAriaLabel(elem);
    return new_code_indent;
  }
  /** Redraws the tab stops in the solution box if this.config.canIndent */
  redrawTabStops() {
    if (!this.config.canIndent) return;

    let max_code_indent = 0;
    this.getSolutionLines().forEach(function (line) {
      max_code_indent = Math.max(max_code_indent, line.code_indent);
    });
    const [backgroundColor, tabStopColor] = [
      "var(--code-background)",
      "var(--pln-txt-color-faded)",
    ];
    const [solidTabStops, dashedTabStop] = [
      `linear-gradient(${tabStopColor}, ${tabStopColor}) no-repeat border-box, `.repeat(
        max_code_indent,
      ),
      `repeating-linear-gradient(0,${tabStopColor},${tabStopColor} 10px,${backgroundColor} 10px,${backgroundColor} 12px) no-repeat border-box`,
    ];
    let backgroundPosition = "";
    for (let i = 1; i <= max_code_indent + 1; i++) {
      backgroundPosition += i * this.config.xIndent + "ch 0, ";
    }
    $(this.config.solutionList).css({
      background: ParsonsGlobal.uiConfig.showNextTabStop
        ? solidTabStops + dashedTabStop
        : solidTabStops.slice(0, -2),
      "background-size": "1px 100%, ".repeat(max_code_indent + 1).slice(0, -2),
      "background-position": backgroundPosition.slice(0, -2),
      "background-origin": "padding-box, "
        .repeat(max_code_indent + 1)
        .slice(0, -2),
      "background-color": backgroundColor,
    });
  }
  storeStudentProgress() {
    const starterElements = this.getSourceLines().map((line, idx) =>
      this.codelineSummary(line, idx),
    );
    const $$ = (selector) => {
      const s = $(selector);
      if (!s.length)
        alert("Could not save student data!\nStorage missing at: " + selector);
      return s;
    };
    $$(this.config.starterOrderStorage).val(JSON.stringify(starterElements));

    const solutionElements = this.getSolutionLines().map((line, idx) =>
      this.codelineSummary(line, idx),
    );
    $$(this.config.solutionOrderStorage).val(JSON.stringify(solutionElements));

    $$(this.config.solutionSubmissionStorage).val(
      this.getSolutionCode().solution,
    );
  }
  toggleDarkmode() {
    $(this.config.main)
      .find(ParsonsGlobal.prettifyOutputClasses)
      .add($(this.config.main))
      .each((_, e) => $(e).toggleClass("dark"));
  }
  updateAriaLabel(codeline, announce = true) {
    // todo:
    //   make each codeline *not* be tagged as a group
    //   each announcement should not read out other list items
    //   get the priority level correct with aria-live so announcements are accurate
    //    - gpt recommends creating an invisible announcement div, and updating its contents as need be
    const lineNumber =
      1 +
      $(codeline.parentElement)
        .children()
        .toArray()
        .findIndex((e) => e == codeline);
    const inStarterTray = $(this.config.starterList).has(codeline).length;
    const indentPrefix = inStarterTray
      ? "unused"
      : `indent ${this.getCodelineIndent(codeline)}`;
    const clone = $(codeline).clone();
    clone
      .find("input")
      .each((_, inp) =>
        inp.replaceWith(inp.value ? `full-blank(${inp.value})` : "empty-blank"),
      );
    const text = clone[0].innerText.trim();
    const label = `line ${lineNumber} ${indentPrefix}: ${text}`;
    // todo: polite seems to be the wrong setting here.
    if (announce) $(codeline).attr("aria-live", "polite");
    $(codeline).attr("aria-label", label);
    if (announce) $(codeline).attr("aria-live", "off");
  }
  addLogEntry() {}
  clearFeedback() {}
}

/////////////////////////////////////////////////////////////////////////////////////////////
window.ParsonsGlobal = window.ParsonsGlobal || {
  // ensure singleton //
  makeLogger: false,
  widgets: [],
  prettifyOutputClasses: [
    "prettyprint",
    "linenums",
    "pln",
    "str",
    "kwd",
    "com",
    "typ",
    "lit",
    "dec",
    "var",
    "pun",
    "opn",
    "clo",
    "tag",
    "atn",
    "atv",
    "fun",
    "L0",
    "L1",
    "L3",
    "L4",
    "L5",
    "L6",
    "L7",
    "L8",
    "L9",
  ]
    .map((cls) => `.${cls}`)
    .join(","),
  uiConfig: {
    /** When true, a Tab in a fading blank always indents,
     *  otherwise a tab will attempt to advance to the next blank
     *  in the codeline before it changes indents
     */
    alwaysIndentOnTab: true,
    /** Toggles the indicator for the next unused tab stop */
    showNextTabStop: false,
  },
  charWidthInPx: (function () {
    const context = document.createElement("canvas").getContext("2d");
    context.font = "monospace";
    return context.measureText("0").width;
  })(),
  getWidget(uuid) {
    return ParsonsGlobal.widgets.find((w) => w.config.uuid == uuid);
  },
  toggleDarkmode() {
    ParsonsGlobal.widgets.forEach((w) => w.toggleDarkmode());
  },
};
