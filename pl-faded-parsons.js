/** expects a config with a `uuid` and fields that align with this schema:
 * ```
 *  ...
 *  <div#{{config.main}}.fpp-global-defs>
 *    <!-- inputs in the template that will save
 *         the student's progress between reloads
 *    -->
 *    <input#{{config.solutionOrderStorage}}
 *    <input#{{config.starterOrderStorage}}
 *    <input#{{config.solutionSubmissionStorage}}
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
    // immediately rebind because jquery does funky stuff to this bindings
    const widget = this;
    widget.config = jQuery.extend(
      {
        xIndent: 4,
        canIndent: true,
        prettyPrint: true,
        onSortableUpdate: (_event, _ui) => {},
        onBlankUpdate: (_event, _input) => {},
      },
      config,
    );

    /** When true, navigating to a codeline with arrow keys enters its first blank */
    widget.enterBlankOnCodelineFocus = true;

    widget.validateConfig();

    // add the toolbar button bindings /////////////////////////////////////////
    {
      $(widget.config.toolbar)
        .find(`.widget-help`)
        .popover({
          content: () =>
            // changes here should be reflected in keyMotionModifiers!
            [
              "Use the mouse or keyboard to rearrange and reindent the lines of code and then fill in the blanks.",
              "Arrow Keys: Select",
              "Alt/Opt+Arrow Keys: Reorder",
              "(Shift+)Tab: Down/Up Indent",
              "(Shift+)Enter: Enter Prev/Next Blank",
            ].join("<br>"),
        });

      $(widget.config.toolbar)
        .find(`.widget-copy`)
        .on({
          click: () => {
            if (navigator.clipboard) {
              navigator.clipboard
                .writeText(widget.asPlaintext())
                .catch((err) => {
                  console.error("Unable to copy text to clipboard", err);
                  alert("Your browser blocked clipboard write access :(");
                });
            } else {
              alert("Your browser does not yet support this :(");
            }
          },
        });

      $(widget.config.toolbar)
        .find(".widget-dark")
        .on({ click: () => ParsonsGlobal.toggleDarkmode() });
    } // end toolbar button setup

    // make solution and starter tray sortable, and linked together ////////////
    {
      /** Does the arithmetic to update the indent after a drag motion */
      const updateIndentAfterDrag = (ui) => {
        const { item, position } = ui;
        const codeline = item[0];
        const pxDelta = position.left - item.parent().position().left;
        const charDelta = pxDelta / ParsonsGlobal.charWidthInPx;
        const levelDelta = Math.floor(charDelta / widget.config.xIndent);
        let newIndent = widget.getCodelineIndent(codeline) + levelDelta;
        newIndent = Math.max(0, newIndent);
        widget.updateIndent(codeline, newIndent, true);
      };
      /** Determines if the moved codeline changed trays */
      const landedInAnotherTray = (e, ui) => e.target != ui.item.parent()[0];

      const starterTray = $(widget.config.starterList); // may not exist!
      const solutionTray = $(widget.config.solutionList);

      const grid = widget.config.canIndent && [widget.config.xIndent, 1];

      // ok if DNE, does nothing
      starterTray.sortable({
        connectWith: solutionTray,
        start: (_, ui) => setCodelineInMotion(ui.item, true),
        receive: (_, ui) =>
          widget.addLogEntry({ type: "removeOutput", target: ui.item }, true),
        stop: (event, ui) => {
          setCodelineInMotion(ui.item, false);

          if (landedInAnotherTray(event, ui)) return;

          widget.addLogEntry({ type: "moveInput", target: ui.item }, true);
        },
        grid: ParsonsGlobal.uiConfig.allowIndentingInStarterTray && grid,
      });

      solutionTray.sortable({
        connectWith: starterTray, // ok if DNE, does nothing
        start: (_, ui) => setCodelineInMotion(ui.item, true),
        stop: (event, ui) => {
          setCodelineInMotion(ui.item, false);

          if (landedInAnotherTray(event, ui)) return;

          updateIndentAfterDrag(ui);

          widget.addLogEntry({ type: "moveOutput", target: ui.item }, true);
        },
        receive: (_, ui) => {
          updateIndentAfterDrag(ui);
          widget.addLogEntry({ type: "addOutput", target: ui.item }, true);
        },
        update: (e, ui) => widget.config.onSortableUpdate(e, ui),
        grid: grid,
      });
    } // end solution and start tray setup

    // make keyboard interactivity helper functions ///////////////////////////

    /**
     * Matches bindings in widget help text!
     * @param e {KeyboardEvent}
     */
    const keyMotionData = (e) => ({
      /** move the codeline under the cursor */
      moveCodeline: e.altKey,
      /** move to the last location */
      moveToEnd: e.ctrlKey || e.metaKey,
      /** shift is not down */
      jumpForward: !e.shiftKey,
      /** arrow direction is `"Right"` or `"Down"` */
      moveForward: e.key === "ArrowRight" || e.key === "ArrowDown",
    });

    /** Finds the blanks within a query subject */
    const findBlanksIn = (codeline) => $(codeline).find("input.parsons-blank");

    /** Manages the codeline's `.codeline-in-motion` css class */
    const setCodelineInMotion = (codeline, inMotion) =>
      $(codeline).toggleClass("codeline-in-motion", inMotion);

    widget.getCodelineInMotion = (codeline) =>
      $(codeline).hasClass("codeline-in-motion");

    /**
     * Takes a codeline or codeline-query and focuses either on its blanks
     * (if `widget.autoEnterBlank` and if it has one) or on the codeline itself.
     */
    const focusCodeline = (codeline, firstBlankNotLast = true) => {
      let target = $(codeline);
      if (!target.exists()) return;
      if (widget.enterBlankOnCodelineFocus) {
        const blanks = findBlanksIn(target);
        const blank = firstBlankNotLast ? blanks.first() : blanks.last();
        target = blank.or(target);
      }
      target.focus();
    };

    /**
     * Returns the result of a search for the codeline in searchTray that is
     * centered closest to the given codeline's center. (i.e find the codeline
     * that has a y-midpoint closest to the moving line's y-midpoint.)
     */
    const findHorizontalTarget = (codeline, searchTray) => {
      const getMiddleY = (domObj) => {
        const { top, bottom } = domObj.getBoundingClientRect();
        return (top + bottom) / 2.0;
      };

      const middle = getMiddleY(codeline);
      const target = $(searchTray)
        .find("li.codeline")
        .minBy((_, line) => Math.abs(middle - getMiddleY(line)));

      const found = target.exists();
      const targetIsLower = found ? getMiddleY(target[0]) > middle : undefined;

      return { found, targetIsLower, target };
    };

    /** Move codeline (or just cursor) horizontally across trays */
    const moveHorizontally = (codeline, { moveForward, moveCodeline }) => {
      // find the tray that we will move the codeline into (works for arbitrary m)
      const codeboxes = $(widget.config.main).find("div.codeline-tray");
      const m = codeboxes.length;
      if (m < 2) return;
      const codeboxIdx = codeboxes
        .toArray()
        .findIndex((c) => $(c).has(codeline).exists());
      const k = codeboxIdx + (moveForward ? +1 : -1);
      if (k < 0 || m <= k) return; // don't wrap around!
      const newTray = codeboxes.eq(k).find("ul.codeline-list");

      const { found, targetIsLower, target } = findHorizontalTarget(
        codeline,
        newTray,
      );

      if (!moveCodeline) {
        focusCodeline(target, moveForward);
        return;
      }

      // capture active element (like blank) to re-focus on after motion
      const selection = $(document.activeElement).or(codeline);

      if (found) {
        if (targetIsLower) {
          $(codeline).insertBefore(target);
        } else {
          $(codeline).insertAfter(target);
        }
      } else {
        $(newTray).append(codeline);
      }

      $(selection).focus();
    };

    /**
     * Navigates cursor horizontally, advancing between blanks and across
     * trays/codelines as necessary. Returns `true` if a special motion
     * happened, `false` otherwise.
     */
    const moveCursorInBlankHorizontally = (
      e,
      codeline,
      blankIdx,
      { moveForward },
    ) => {
      const codelineBlanks = findBlanksIn(codeline);
      const blank = codelineBlanks.get(blankIdx);
      // if user selecting text, return allowing default
      if (blank.selectionEnd != blank.selectionStart) return false;

      const cursorIdx = blank.selectionStart;
      const [lastTextIdx, lastBlankIdx, blankDelta] = moveForward
        ? [blank.value.length, codelineBlanks.length - 1, +1]
        : [0, 0, -1];

      // if cursor not on the edge of a blank, return allowing default
      if (cursorIdx != lastTextIdx) return false;

      // we are on the edge of a blank, and not selecting text,
      // so we don't want the cursor to move normally.
      e.preventDefault();

      // if the blank is the first/last in the row...
      if (blankIdx == lastBlankIdx) {
        // then move cursor between codelines
        moveHorizontally(codeline, { moveForward, moveCodeline: true });
      } else {
        // otherwise move cursor between blanks within the codeline.
        // if exitting rightward, then enter on left, and vice-versa
        codelineBlanks
          .eq(blankIdx + blankDelta)
          .focus()
          .each((_, input) => {
            const l = moveForward ? 0 : input.value.length;
            input.setSelectionRange(l, l);
          });
      }
      return true;
    };

    const jumpToNextBlank = (blank, { jumpForward }) => {
      const delta = jumpForward ? +1 : -1;
      const allBlanks = findBlanksIn(widget.config.main);
      const m = allBlanks.length;
      const nextIndex = (allBlanks.index(blank) + m + delta) % m;
      allBlanks.eq(nextIndex).focus();
    };

    /**
     * Moves a codeline up/down in its own tray.
     * Will not move if the codeline is stuck at the top/bottom.
     * Setting `moveToEnd` will jump a codeline to the top/bottom.
     * Setting `cursorOnly` does not reorder lines, only moves the cursor.
     */
    const moveVertically = (
      codeline,
      { moveForward, moveToEnd, moveCodeline },
    ) => {
      const parent = $(codeline).parent();
      const children = parent.children();
      const index = children.index(codeline);
      const [delta, invalidIdx] = moveForward
        ? [+1, children.length - 1]
        : [-1, 0];
      if (index === invalidIdx) return;

      const nextChild = children.eq(index + delta);

      if (!moveCodeline) {
        const extremeChild = moveForward ? children.last() : children.first();
        focusCodeline(moveToEnd ? extremeChild : nextChild);
        return;
      }

      // capture active element (like blank) to re-focus on after motion
      const selection = $(document.activeElement).or(codeline);

      if (moveToEnd) {
        if (moveForward) {
          parent.append(codeline);
        } else {
          parent.prepend(codeline);
        }
      } else {
        if (moveForward) {
          nextChild.insertBefore(codeline);
        } else {
          nextChild.insertAfter(codeline);
        }
      }

      $(selection).focus();
    };

    const onCodelineKeydown = (e, codeline) => {
      const motionData = keyMotionData(e);
      setCodelineInMotion(codeline, motionData.moveCodeline);

      if (!$(codeline).is(":focus")) return;

      // Tab/Shift+Tab to Indent/Dedent,
      // or Tab out of Starter Tray into Codeline
      if (e.key === "Tab") {
        e.preventDefault();
        const moveInsteadOfIndent =
          !ParsonsGlobal.uiConfig.allowIndentingInStarterTray &&
          motionData.jumpForward &&
          $(widget.config.starter).has(codeline).exists(); // in starter tray?
        if (moveInsteadOfIndent) {
          moveHorizontally(codeline, {
            moveForward: true,
            moveCodeline: false,
          });
        } else {
          const delta = motionData.jumpForward ? +1 : -1;
          widget.updateIndent(codeline, delta, false);
        }
        return;
      }

      // Enter to refocus on the blanks
      if (e.key === "Enter") {
        e.preventDefault();
        findBlanksIn(codeline).first().focus();
        widget.enterBlankOnCodelineFocus = true;
        return;
      }

      // Escape removes focus
      if (e.key === "Escape") {
        e.preventDefault();
        $(codeline).blur();
        widget.enterBlankOnCodelineFocus = false;
        return;
      }

      // (Alt/Option)+Arrow to Reorder Lines, Arrow to Navigate
      switch (e.key) {
        case "ArrowLeft":
        case "ArrowRight":
          e.preventDefault();
          moveHorizontally(codeline, motionData);
          return;
        case "ArrowUp":
        case "ArrowDown":
          e.preventDefault();
          moveVertically(codeline, motionData);
          return;
      }
    };

    const onBlankKeydown = (e, codeline, blank) => {
      const blanks = findBlanksIn(codeline);
      const blankIdx = blanks.index(blank);
      const motionData = keyMotionData(e);
      // Tab/Shift+Tab to Indent/Dedent if on the first/last blank of line,
      // otherwise advance/retreat blanks on the line
      if (e.key === "Tab") {
        const [boundary, delta] = motionData.jumpForward
          ? [blanks.length - 1, +1]
          : [0, -1];
        if (ParsonsGlobal.uiConfig.alwaysIndentOnTab || blankIdx == boundary) {
          e.preventDefault();
          widget.updateIndent(codeline, delta, false);
        }
        return;
      }
      // Escape to loose focus on the blank
      if (e.key === "Escape") {
        $(codeline).focus();
        e.stopPropagation();
        widget.enterBlankOnCodelineFocus = false;
        return;
      }
      // Enter/Shift+Enter to advance/retreat blanks
      if (e.key === "Enter") {
        e.preventDefault();
        widget.enterBlankOnCodelineFocus = true;
        jumpToNextBlank(blank, motionData);
        return;
      }
      // (Alt/Option)+Arrow to Reorder Lines
      // Arrow Up/Down to Navigate Lines
      // Arrow Right/Left to move cursor (including between input boxes)
      switch (e.key) {
        case "ArrowUp":
        case "ArrowDown":
          e.preventDefault();
          moveVertically(codeline, motionData);
          return;
        case "ArrowRight":
        case "ArrowLeft":
          if (motionData.moveCodeline) {
            e.preventDefault();
            moveHorizontally(codeline, motionData);
          } else {
            moveCursorInBlankHorizontally(e, codeline, blankIdx, motionData);
          }
          return;
      }
    };

    // init gui ///////////////////////////////////////////////////////////////
    {
      widget.redrawTabStops();

      $("form.question-form").submit(() => widget.storeStudentProgress());

      // resize blanks to fit text
      findBlanksIn(widget.config.main).each((_, blank) =>
        widget.autoSizeBlank(blank),
      );
    }

    // add interactivity to codelines and blanks //////////////////////////////

    $(widget.config.main)
      .find("li.codeline")
      // fix the aria labels
      .each((_, codeline) => widget.updateAriaLabel(codeline, false))
      // setup callbacks on each codeline (this)
      .on({
        focus() {
          widget.updateAriaLabel(this);
        },
        blur() {
          widget.updateAriaLabel(this, false);
          setCodelineInMotion(this, false);
        },
        click(e) {
          if (e.target != this) return; // if child clicked, return.
          widget.enterBlankOnCodelineFocus = false;
          focusCodeline(this);
          widget.updateAriaLabel(this);
        },
        keyup(e) {
          const { moveCodeline } = keyMotionData(e);
          setCodelineInMotion(this, moveCodeline);
          widget.updateAriaLabel(this);
        },
        keydown(e) {
          onCodelineKeydown(e, this);
          widget.updateAriaLabel(this);
        },
      })
      // setup callbacks on each blank (this) in every codeline
      .each((_, codeline) =>
        findBlanksIn(codeline).on({
          focus() {
            widget.enterBlankOnCodelineFocus = true;
            widget.updateAriaLabel(codeline);
          },
          input(e) {
            widget.autoSizeBlank(this);
            widget.updateAriaLabel(codeline);
            widget.config.onBlankUpdate(e, this);
          },
          keyup(e) {
            const { moveCodeline } = keyMotionData(e);
            setCodelineInMotion(codeline, moveCodeline);
          },
          keydown(e) {
            onBlankKeydown(e, codeline, this);
            widget.updateAriaLabel(codeline);
          },
        }),
      );
  }
  validateConfig() {
    if (this.config.prettyPrint) {
      if (window.prettyPrint) {
        window.prettyPrint();
      } else {
        console.error("prettify bindings missing!");
      }
    }

    const missing = [
      "uuid",
      "solution",
      "solutionList",
      "main",
      "toolbar",
      "starterOrderStorage",
      "solutionOrderStorage",
      "solutionSubmissionStorage",
    ]
      .filter((f) => this.config[f] == null)
      .join(", ");

    if (missing)
      throw new Error(
        `ParsonsWidget config requires field(s) ${missing} to be non-null`,
      );
  }
  /** Returns the indentation level of the codeline */
  getCodelineIndent(codeline) {
    // for some reason, $.css and $.cssUnit report values only in px in amounts
    // that do not align with ParsonsGlobal.charWidthInPx... just use DOM API.
    const indentChar = parseInt(
      codeline.style && codeline.style.marginLeft,
      10,
    );
    const indentLevel = indentChar / this.config.xIndent;
    return isNaN(indentLevel) ? 0 : indentLevel;
  }
  getCodelineSegments(codeline) {
    let elemClone = $(codeline).clone();
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
  autoSizeBlank(el) {
    $(el).width(el.value.length.toString() + "ch");
  }
  getSourceLines() {
    return $(this.config.starterList).children().toArray();
  }
  getSolutionLines() {
    return $(this.config.solutionList).children().toArray();
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
  updateIndent(codeline, newCodeIndent, absolute = true) {
    if (!this.config.canIndent) return;

    let oldCodeIndent = this.getCodelineIndent(codeline);
    if (!absolute) newCodeIndent += oldCodeIndent;

    if (oldCodeIndent != newCodeIndent && newCodeIndent >= 0) {
      this.config.onSortableUpdate(
        {
          type: "reindent",
          content: this.getCodelineText(codeline),
          old: oldCodeIndent,
          new: newCodeIndent,
        },
        this.getSolutionLines(),
      );

      $(codeline).css(
        "margin-left",
        this.config.xIndent * newCodeIndent + "ch",
      );

      this.redrawTabStops();
    }
    this.updateAriaLabel(codeline);
    return newCodeIndent;
  }
  /** Redraws the tab stops in the solution box if this.config.canIndent */
  redrawTabStops() {
    if (!this.config.canIndent || !ParsonsGlobal.uiConfig.showTabStops) return;

    const max_code_indent = this.getSolutionLines()
      .map((line) => this.getCodelineIndent(line))
      .reduce((x, y) => Math.max(x, y), 0);
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
    const $orAlert = (selector) => {
      const s = $(selector);
      if (!s.exists()) {
        const msg =
          "Could not save student data!\nStorage missing at: " + selector;
        console.error(msg);
        alert(msg);
      }
      return s;
    };
    $orAlert(this.config.starterOrderStorage).val(
      JSON.stringify(starterElements),
    );

    const solutionElements = this.getSolutionLines().map((line, idx) =>
      this.codelineSummary(line, idx),
    );
    $orAlert(this.config.solutionOrderStorage).val(
      JSON.stringify(solutionElements),
    );

    $orAlert(this.config.solutionSubmissionStorage).val(
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
    const lineNumber = 1 + $(codeline.parentElement).children().index(codeline);
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
}

/////////////////////////////////////////////////////////////////////////////////////////////
window.ParsonsGlobal ||= /* singleton! */ {
  makeLogger: false,
  widgets: [],
  prettifyOutputClasses:
    ".prettyprint,.linenums,.pln,.str,.kwd,.com,.typ,.lit,.dec,.var,.pun,.opn,.clo,.tag,.atn,.atv,.fun,.L0,.L1,.L3,.L4,.L5,.L6,.L7,.L8,.L9",
  uiConfig: {
    /**
     * When true, a Tab in a fading blank always indents,
     * otherwise a tab will attempt to advance to the next blank
     * in the codeline before it changes indents
     */
    alwaysIndentOnTab: true,
    /** Toggles the indicator for the next unused tab stop */
    showNextTabStop: false,
    /** Toggles displaying tab stop altogether */
    showTabStops: false,
    /**
     * When true, a Tab indents a codeline in the codetray
     * instead of advancing it into the next tray
     */
    allowIndentingInStarterTray: false,
  },
  /** The custom methods that are added to jQuery results */
  jqueryExtension: (function ($) {
    const extension = {
      /** True if the query has results */
      exists() {
        return this.length !== 0;
      },
      /** If the query is empty, return alt, otherwise return this */
      or(alt) {
        return this.exists() ? this : alt;
      },
      /** Filters for the (first) minimum element by keyFn(index, elem) */
      minBy(keyFn) {
        let out = 0,
          i = 0,
          min = Infinity;
        for (let item of this) {
          const key = keyFn(i, item);
          if (key < min) {
            min = key;
            out = i;
          }
          if (key === -Infinity) break;
          i++;
        }
        return this.eq(out);
      },
    };
    $.fn.extend(extension);
    return extension;
  })(jQuery),
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
