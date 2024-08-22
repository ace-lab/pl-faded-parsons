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
 *         <ol#{{config.starterList}}.codeline-list>
 *           <li.codeline> ... <input.parsons-blank>* ... </li>*
 *         </ol>
 *       </div>
 *   )?
 *    ...
 *    <div#{{config.solution}}.codeline-tray>
 *       <ol#{{config.solutionList}}.codeline-list>
 *         <li.codeline> ... <input.parsons-blank>* ... </li>*
 *       </ol>
 *    </div>
 *     ...
 *    <div#{{config.toolbar}>
 *       ...
 *       <div.fpp-help></div>
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
          placement: "auto",
          trigger: "focus",
          html: true,
          title: "Faded Parsons Help",
          content:
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
        .popover({
          placement: "auto",
          trigger: "focus",
          content: "Copied to Clipboard!",
        })
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
          widget.addLogEntry("removeOutput", widget.codelineSummary(ui.item)),
        stop: (event, ui) => {
          setCodelineInMotion(ui.item, false);
          widget.storeStudentProgress();

          if (landedInAnotherTray(event, ui)) return;

          widget.addLogEntry("moveInput", widget.codelineSummary(ui.item));
        },
        grid: ParsonsGlobal.uiConfig.allowIndentingInStarterTray && grid,
      });

      solutionTray.sortable({
        connectWith: starterTray, // ok if DNE, does nothing
        start: (_, ui) => setCodelineInMotion(ui.item, true),
        stop: (event, ui) => {
          setCodelineInMotion(ui.item, false);
          widget.storeStudentProgress();

          if (landedInAnotherTray(event, ui)) return;

          updateIndentAfterDrag(ui);

          widget.addLogEntry("moveOutput", widget.codelineSummary(ui.item));
        },
        receive: (_, ui) => {
          updateIndentAfterDrag(ui);
          widget.addLogEntry("addOutput", widget.codelineSummary(ui.item));
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

    widget.findBlanksIn = findBlanksIn;

    /** Manages the codeline's drag state */
    const setCodelineInMotion = (codeline, inMotion) =>
      $(codeline)
        .attr("aria-grabbed", inMotion)
        .toggleClass("codeline-in-motion", inMotion);

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
      const codeboxes = $(widget.config.main).find(".codeline-tray");
      const m = codeboxes.length;
      if (m < 2) return;
      const codeboxIdx = codeboxes
        .toArray()
        .findIndex((c) => $(c).has(codeline).exists());
      const k = codeboxIdx + (moveForward ? +1 : -1);
      if (k < 0 || m <= k) return; // don't wrap around!
      const newTray = codeboxes.eq(k).find(".codeline-list");

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
        moveHorizontally(codeline, { moveForward, moveCodeline: false });
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
     * Setting `moveCodeline` reorders lines with the cursor.
     */
    const moveVertically = (
      codeline,
      { moveForward, moveToEnd, moveCodeline },
    ) => {
      const parent = $(codeline).parent();
      const nextChild = moveForward ? $(codeline).next() : $(codeline).prev();

      if (!nextChild.exists()) return;

      if (!moveCodeline) {
        const children = parent.children();
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
            moveCodeline: true,
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

      // attaching to submit causes "Warning: Unsaved Changes" alerts
      // even when there's no unsaved changes...
      // $("form.question-form").submit(() => widget.storeStudentProgress());
      widget.storeStudentProgress();

      // resize blanks to fit text
      findBlanksIn(widget.config.main).each((_, blank) =>
        widget.autoSizeBlank(blank),
      );
    }

    // ready the aria accessibility ///////////////////////////////////////////
    {
      const descriptor = $(widget.config.ariaDescriptor);
      const details = $(widget.config.ariaDetails);
      if (ParsonsGlobal.uiConfig.showAriaDescriptor) {
        descriptor.css("display", "inline-block");
        details.css("display", "inline-block");
      }

      $(widget.config.main)
        .find("li.codeline")
        .attr("aria-labelledby", descriptor.attr("id"))
        .attr("aria-details", details.attr("id"));

      findBlanksIn(widget.config.main)
        .attr("aria-labelledby", descriptor.attr("id"))
        .attr("aria-details", details.attr("id"));
    }

    // add interactivity to codelines and blanks //////////////////////////////

    $(widget.config.main)
      .find("li.codeline")
      // fix the aria labels
      .each((_, codeline) => widget.updateAriaInfo(codeline, false))
      // setup callbacks on each codeline (this)
      .on({
        focus() {
          widget.updateAriaInfo(this);
        },
        blur() {
          setCodelineInMotion(this, false);
          widget.updateAriaInfo(this, false);
        },
        click(e) {
          if (e.target != this) return; // if child clicked, return.
          widget.enterBlankOnCodelineFocus = false;
          focusCodeline(this);
        },
        keyup(e) {
          const { moveCodeline } = keyMotionData(e);
          setCodelineInMotion(this, moveCodeline);
          widget.updateAriaInfo(this);
        },
        keydown(e) {
          onCodelineKeydown(e, this);
          widget.updateAriaInfo(this);
          widget.storeStudentProgress();
        },
      })
      // setup callbacks on each blank (this) in every codeline
      .each((_, codeline) =>
        findBlanksIn(codeline).on({
          focus() {
            widget.enterBlankOnCodelineFocus = true;
            widget.updateAriaInfo(codeline);
          },
          input(e) {
            widget.autoSizeBlank(this);
            widget.storeStudentProgress();
            widget.config.onBlankUpdate(e, this);
          },
          keydown(e) {
            onBlankKeydown(e, codeline, this);
            widget.storeStudentProgress();
          },
        }),
      );

    // add uids to each line and blank for logging ////////////////////////////
    $(widget.config.main)
      .find(".codeline-tray")
      .each((trayNumber, tray) =>
        $(tray)
          .find("li.codeline")
          .each((codelineNumber, codeline) => {
            if ($(codeline).attr("logging-id")) return;
            const codelineId = `${trayNumber}.${codelineNumber}`;
            $(codeline).attr("logging-id", codelineId);
            findBlanksIn(codeline).each((blankNumber, blank) => {
              $(blank).attr("logging-id", `${codelineId}.${blankNumber}`);
            });
          }),
      );

    //  add logging hooks for blank edits  //////////////////////////////////
    findBlanksIn(widget.config.main).on({
      input(e) {
        widget.addLogEntry("editBlank", {
          value: $(e.target).val(),
          id: $(e.target).attr("logging-id"),
        });
      },
    });

    widget.addLogEntry("problemOpened", {});
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
      "logStorage",
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
    codeline = $(codeline).get(0);
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
    this.findBlanksIn(elemClone).each(function (_, inp) {
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
    if (idx == null) {
      idx = line.index();
    }

    return {
      // this schema is used in pl-faded-parsons.py `read_lines`!
      content: this.getCodelineText(line),
      indent: this.getCodelineIndent(line),
      segments: this.getCodelineSegments(line),
      id: $(line).attr("logging-id"),
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
      this.findBlanksIn(lineClone).each(function (_, inp) {
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
    this.findBlanksIn(elemClone).each(function (_, inp) {
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
    this.updateAriaInfo(codeline);
    console.log("update indent");
    this.storeStudentProgress();
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
    const $orErr = (selector) => {
      const s = $(selector);
      if (!s.exists()) {
        console.error(
          "Could not save student data!\nStorage missing at: " + selector,
        );
      }
      return s;
    };
    $orErr(this.config.starterOrderStorage).val(
      JSON.stringify(starterElements),
    );

    const solutionElements = this.getSolutionLines().map((line, idx) =>
      this.codelineSummary(line, idx),
    );
    $orErr(this.config.solutionOrderStorage).val(
      JSON.stringify(solutionElements),
    );

    $orErr(this.config.solutionSubmissionStorage).val(
      this.getSolutionCode().solution,
    );
  }
  toggleDarkmode() {
    $(this.config.main)
      .find(ParsonsGlobal.prettifyOutputClasses)
      .add($(this.config.main))
      .each((_, e) => $(e).toggleClass("dark"));
  }
  updateAriaInfo(codeline, hasFocus = true) {
    const defaultText = "no codeline selected. select a codeline to begin. ";

    $(this.config.ariaDescriptor).text(
      hasFocus ? this.codelineAriaDescription(codeline) : defaultText,
    );

    $(this.config.ariaDetails).text(
      hasFocus
        ? this.codelineAriaDetails(codeline)
        : defaultText +
            "use arrow keys, tab, and enter to navigate and indent." +
            "use shift to reverse motion, and option/ctrl to jump.",
    );
  }
  codelineAriaDetails(codeline) {
    const trays = $(this.config.main).find(".codeline-tray");
    const tray =
      1 + trays.toArray().findIndex((t) => $(t).has(codeline).exists());
    const trayText =
      trays > 1 ? `; All in tray ${tray} of ${trays.length}.` : ".";
    let indentLevel = this.getCodelineIndent(codeline);
    const visualDedentParents = $(codeline)
      .prevAll()
      .filter((_, sib) => {
        const sibIndentLevel = this.getCodelineIndent(sib);
        const sibDedented = sibIndentLevel < indentLevel;
        indentLevel = Math.min(sibIndentLevel, indentLevel);
        return sibDedented;
      })
      .toArray();
    return (
      [codeline, ...visualDedentParents]
        .map((cl) => this.codelineAriaDescription(cl))
        .join("; Under ") + trayText
    );
  }
  codelineAriaDescription(codeline) {
    const lineUiDescription = (codeline) => {
      const motionText = this.getCodelineInMotion(codeline) ? "moving " : "";
      const lineNumber = 1 + $(codeline).parent().children().index(codeline);
      return `${motionText} line ${lineNumber}`;
    };
    const indentDescription = (codeline) => {
      const inStarterTray = $(this.config.starterList).has(codeline).exists();
      const prefix = inStarterTray ? "unused, " : "";
      const tabs = this.getCodelineIndent(codeline);
      return (
        prefix + (tabs === 0 ? "flush" : tabs === 1 ? "tab" : `${tabs} tabs`)
      );
    };
    const bodyDescription = (codeline) => {
      const fIdx = this.findBlanksIn(codeline).index(document.activeElement);
      const formatBlank = (idx, inp) => {
        const value = inp.value ? `(${inp.value})` : "";
        const header = idx === fIdx ? "active" : value ? "full" : "empty";
        return inp.replaceWith(`${header}-blank${value}`);
      };

      const clone = $(codeline).clone();
      this.findBlanksIn(clone).each(formatBlank);
      return clone.text().trim();
    };
    const lineUIDesc = lineUiDescription(codeline);
    const indentDesc = indentDescription(codeline);
    const bodyDesc = bodyDescription(codeline);
    return `${lineUIDesc}, ${indentDesc}, ${bodyDesc}`;
  }
  /** Add a tagged, timestamped log entry to `this.config.logStorage` */
  addLogEntry(tag, data) {
    const timestamp = new Date();

    const entry = { timestamp, tag, data };

    const s = $(this.config.logStorage);
    if (!s.exists()) {
      const msg = "Could not save log!\nStorage missing at: " + selector;
      console.error(msg);
      alert(msg);
      return;
    }

    let prev_log = s.val();
    prev_log = JSON.parse(prev_log);
    if (prev_log == null) {
      prev_log = [];
    } else if (!Array.isArray(prev_log)) {
      prev_log = [prev_log];
    }

    prev_log.push(entry);
    s.val(JSON.stringify(prev_log));
  }
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
    /** Toggles the visibility of the aria-describedby and aria-details divs */
    showAriaDescriptor: false,
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
