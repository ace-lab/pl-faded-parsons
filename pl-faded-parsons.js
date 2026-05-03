function buildWidgetConfig(config) {
  return jQuery.extend(
    {
      xIndent: 4,
      canIndent: true,
      maxIndentLevel: 5,
      visualIndent: 0,
      prettyPrint: true,
      loggingEnabled: false,
      onSortableUpdate: (_event, _ui) => {},
      onBlankUpdate: (_event, _input) => {},
    },
    config,
  );
}

function buildToolbarHelpContent() {
  return [
    "The code in the tray on the right is the solution that will be submitted.",
    "Use the mouse or keyboard to rearrange and reindent the code-lines and then fill in the blanks.",
    "Arrow Keys: Select",
    "Alt/Opt+Arrow Keys: Reorder",
    "(Shift+)Tab: Down/Up Indent",
    "(Shift+)Enter: Enter Prev/Next Blank",
  ].join("<br>");
}

function getKeyMotionData(e) {
  return {
    /** move the codeline under the cursor */
    moveCodeline: e.altKey,
    /** move to the last location */
    moveToEnd: e.ctrlKey || e.metaKey,
    /** shift is not down */
    jumpForward: !e.shiftKey,
    /** arrow direction is `"Right"` or `"Down"` */
    moveForward: e.key === "ArrowRight" || e.key === "ArrowDown",
  };
}

function getCurrentDragTray(ui) {
  return ui?.placeholder?.parent?.() ?? ui?.item?.parent?.();
}

function getPageLeft(target) {
  const element = target?.[0] ?? target;
  if (!element) return undefined;

  const rect = element.getBoundingClientRect?.();
  if (rect) {
    return rect.left + (window.scrollX ?? window.pageXOffset ?? 0);
  }

  const offsetLeft = $(element).offset?.()?.left;
  if (offsetLeft != null) return offsetLeft;

  const positionLeft = $(element).position?.()?.left;
  return positionLeft;
}

const DRAG_START_TRAY_KEY = "__plFppDragStartTray";

function getDragTray(ui) {
  return ui?.item?.parent?.()?.[0];
}

function rememberDragStartTray(ui) {
  const codeline = ui?.item?.[0];
  if (!codeline) return;
  codeline[DRAG_START_TRAY_KEY] = getDragTray(ui);
}

function forgetDragStartTray(ui) {
  const codeline = ui?.item?.[0];
  if (!codeline) return;
  delete codeline[DRAG_START_TRAY_KEY];
}

function draggedFromAnotherTray(ui) {
  const codeline = ui?.item?.[0];
  const startTray = codeline?.[DRAG_START_TRAY_KEY];
  const endTray = getDragTray(ui);
  return startTray != null && startTray !== endTray;
}

function landedInAnotherTray(e, ui) {
  return draggedFromAnotherTray(ui) || e.target != getDragTray(ui);
}

const PRETTIFY_OUTPUT_CLASSES =
  ".prettyprint,.linenums,.pln,.str,.kwd,.com,.typ,.lit,.dec,.var,.pun,.opn,.clo,.tag,.atn,.atv,.fun,.L0,.L1,.L3,.L4,.L5,.L6,.L7,.L8,.L9";

const CHAR_WIDTH_IN_PX = (() => {
  const context = document.createElement("canvas").getContext("2d");
  context.font = "monospace";
  return context.measureText("#").width;
})();

$.fn.extend({
  /** True if the query has results */
  exists() {
    return this.length !== 0;
  },
  /** Throws when a setup-time query that must exist is empty. */
  expectExists(label) {
    const length = this.length ?? 0;
    if (length === 0) {
      const message = `Expected ${label} to exist, but it was missing.`;
      console.error(message);
      throw new Error(message);
    }
    return this;
  },
  /** Throws when a setup-time query that must be unique is missing or duplicated. */
  expectUnique(label) {
    const length = this.length ?? 0;
    if (length !== 1) {
      const message = `Expected ${label} to be unique, but found ${length} matches.`;
      console.error(message);
      throw new Error(message);
    }
    return this;
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
});

/** expects a config with a `uuid` and fields that align with this schema:
 * ```
 *  ...
 *  <div#{{config.main}}.fpp-global-defs>
 *    <!-- inputs in the template that will save
 *         the student's progress between reloads
 *    -->
 *    <input#{{config.storage}}
 *    <input#{{config.logStorage}} <!-- optional if !config.loggingEnabled -->
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
 *    <div#{{config.toolbar}}>
 *       ...
 *       <div.fpp-help></div>
 *       <div.fpp-copy></div> <!-- A copy button is optional -->
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
    widget.config = buildWidgetConfig(config);

    /** When true, navigating to a codeline with arrow keys enters its first blank */
    widget.enterBlankOnCodelineFocus = true;
    /** When true, the widget is in "codeline capture" mode. */
    widget.codelineCaptureActive = false;
    widget.activeSortablePlaceholder = $();

    widget.validateConfig();
    widget.applyVisualIndent();
    widget.setupToolbarBindings();
    widget.setupTraySortables();
    widget.setupCoreDomHelpers();
    widget.setupInitialGuiState();
    widget.setupAccessibilityBindings();
    widget.setupInteractivityBindings();
  }

  /////////////////////////////// CONSTRUCTOR HELPERS ////////////////////////////

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
      "storage",
      "logStorage",
    ]
      .filter((f) => this.config[f] == null)
      .join(", ");

    if (missing)
      throw new Error(
        `ParsonsWidget config requires field(s) ${missing} to be non-null`,
      );
  }

  setupToolbarBindings() {
    const toolbar = $(this.config.toolbar).expectUnique("toolbar");
    const helpButton = toolbar.find(`.widget-help`).expectUnique("widget help");
    const copyButton = toolbar.find(`.widget-copy`);

    helpButton.popover({
      placement: "auto",
      trigger: "focus",
      html: true,
      title: "Faded Parsons Help",
      content: buildToolbarHelpContent(), // changes here should be reflected in keyMotionModifiers!
    });
    helpButton.attr(
      "aria-description",
      buildToolbarHelpContent().replaceAll("<br>", " "),
    );

    copyButton
      .popover({
        placement: "auto",
        trigger: "focus",
        content: "Copied to Clipboard!",
      })
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
  }

  applyVisualIndent() {
    const visualIndent = Number(this.config.visualIndent ?? 0) || 0;
    const visualIndentCorrection = visualIndent > 0 ? "1ch" : "0ch";
    const trays = $(this.config.main).find(".codeline-tray");
    trays.css(
      "--pl-faded-parsons-visual-indent-correction",
      visualIndentCorrection,
    );
    trays.css("--pl-faded-parsons-visual-indent", visualIndent);
  }

  enterCodelineCapture() {
    this.codelineCaptureActive = true;
    this.enterBlankOnCodelineFocus = false;
    this.setCodelinesTabStops(true);
    this.setBlankTabStops(true);
    const solutionLines = this.getSolutionLines();
    const starterLines = this.getSourceLines();
    const firstSolutionLine = solutionLines?.get?.(0) ?? solutionLines?.[0];
    const firstStarterLine = starterLines?.get?.(0) ?? starterLines?.[0];
    this.announceMode?.(
      "Arrow-key mode on. Use arrow keys to move between code-lines and option or alt with arrow keys to move code-lines. Escape returns to tabbing mode.",
    );
    this.focusCodeline(firstSolutionLine || firstStarterLine);
  }

  exitCodelineCapture() {
    this.codelineCaptureActive = false;
    this.enterBlankOnCodelineFocus = false;
    this.setCodelinesTabStops(false);
    this.setBlankTabStops(false);
    this.announceMode?.(
      "Tabbing mode on. Press Enter on the widget to focus the code-lines again.",
    );
    const widgetRoot = $(this.config.main);
    if (widgetRoot.focus) {
      widgetRoot.focus();
    }
  }

  announceMode(message) {
    const liveRegion = $(this.config.ariaDetails);
    liveRegion.attr("aria-busy", "true");
    liveRegion.text("");
    liveRegion.text(message);
    liveRegion.attr("aria-busy", "false");
  }

  setupTraySortables() {
    const updateIndentAfterDrag = (ui) => {
      this.updateIndent(ui.item[0], this.getIndentAtDragPosition(ui), true);
    };

    $(this.config.main).find(".codeline-tray").expectExists("codeline trays");
    const starterTray = $(this.config.starterList);
    const solutionTray = $(this.config.solutionList).expectUnique("solution tray");

    const grid = this.config.canIndent && [
      this.config.xIndent * CHAR_WIDTH_IN_PX,
      1,
    ];
    const sortableOptions = {
      placeholder: "codeline-sortable-placeholder",
      forcePlaceholderSize: true,
      tolerance: "pointer",
    };

    starterTray.sortable({
      connectWith: solutionTray,
      ...sortableOptions,
      start: (_, ui) => {
        this.activeSortablePlaceholder = ui.placeholder;
        ui.item.addClass("codeline-dragging");
        this.setCodelineInMotion(ui.item, true);
        rememberDragStartTray(ui);
        this.syncSortablePlaceholder(ui.item);
      },
      sort: (_, ui) => {
        this.syncSortablePlaceholder(ui.item, this.getIndentAtDragPosition(ui));
      },
      receive: (_, ui) =>
        this.addLogEntry("removeOutput", this.codelineLogEntry(ui.item)),
      stop: (event, ui) => {
        ui.item.removeClass("codeline-dragging");
        this.setCodelineInMotion(ui.item, false);
        forgetDragStartTray(ui);
        this.activeSortablePlaceholder = $();
        this.storeStudentProgress();

        if (landedInAnotherTray(event, ui)) return;

        this.addLogEntry("moveInput", this.codelineLogEntry(ui.item));
      },
    });

    solutionTray.sortable({
      connectWith: starterTray, // ok if DNE, does nothing
      ...sortableOptions,
      start: (_, ui) => {
        this.activeSortablePlaceholder = ui.placeholder;
        ui.item.addClass("codeline-dragging");
        this.setCodelineInMotion(ui.item, true);
        rememberDragStartTray(ui);
        this.syncSortablePlaceholder(ui.item);
      },
      sort: (_, ui) => {
        this.syncSortablePlaceholder(ui.item, this.getIndentAtDragPosition(ui));
      },
      stop: (event, ui) => {
        ui.item.removeClass("codeline-dragging");
        this.setCodelineInMotion(ui.item, false);
        forgetDragStartTray(ui);
        this.activeSortablePlaceholder = $();
        this.storeStudentProgress();

        if (landedInAnotherTray(event, ui)) return;

        updateIndentAfterDrag(ui);

        this.addLogEntry("moveOutput", this.codelineLogEntry(ui.item));
      },
      receive: (_, ui) => {
        updateIndentAfterDrag(ui);
        this.addLogEntry("addOutput", this.codelineLogEntry(ui.item));
      },
      update: (e, ui) => this.config.onSortableUpdate(e, ui),
      grid: grid,
    });
  }

  setupCoreDomHelpers() {
    /** Finds the blanks within a query subject */
    const findBlanksIn = (codeline) => $(codeline).find("input.parsons-blank");

    this.findBlanksIn = findBlanksIn;
    this.setCodelinesTabStops = (tabbable) =>
      $(this.config.main)
        .find("li.codeline")
        .attr("tabindex", tabbable ? "0" : "-1");
    this.setBlankTabStops = (tabbable) =>
      $(this.config.main)
        .find("input.parsons-blank")
        .attr("tabindex", tabbable ? "0" : "-1");

    /** Manages the codeline's drag state */
    this.setCodelineInMotion = (codeline, inMotion) =>
      $(codeline)
        .attr("aria-grabbed", inMotion)
        .toggleClass("codeline-in-motion", inMotion);

    this.getCodelineInMotion = (codeline) =>
      $(codeline).hasClass("codeline-in-motion");
    this.isSortablePlaceholder = (codeline) =>
      $(codeline).hasClass("ui-sortable-placeholder") ||
      $(codeline).hasClass("codeline-sortable-placeholder");
  }

  setupInitialGuiState() {
    this.storeStudentProgress();
    this.findBlanksIn(this.config.main).each((_, blank) =>
      this.autoSizeBlank(blank),
    );
    this.findBlanksIn(this.config.main).each((_, blank) =>
      this.syncMissingBlankState(blank),
    );
    this.setCodelinesTabStops(false);
    this.setBlankTabStops(false);
  }

  setupAccessibilityBindings() {
    const descriptor = $(this.config.ariaDescriptor).expectUnique("aria descriptor");
    const details = $(this.config.ariaDetails).expectUnique("aria details");

    $(this.config.main)
      .attr("aria-labelledby", descriptor.attr("id"))
      .attr("aria-details", details.attr("id"));

    $(this.config.main)
      .find("li.codeline")
      .attr("aria-labelledby", descriptor.attr("id"))
      .attr("aria-details", details.attr("id"))
      .each((_, codeline) => {
        const hasBlanks = this.findBlanksIn(codeline).length > 0;
        $(codeline).attr(
          "aria-roledescription",
          hasBlanks ? null : "code line",
        );
      });

    this.findBlanksIn(this.config.main).attr("aria-label", "code blank");
  }

  setupInteractivityBindings() {
    $(this.config.main)
      .expectUnique("main widget")
      .on({
        focus: (e) => {
          if (e.target !== e.currentTarget) return;
          this.updateAriaInfo(null, false);
        },
        keydown: (e) => {
          if (e.target !== e.currentTarget) return;
          if (e.key !== "Enter") return;
          e.preventDefault();
          this.enterCodelineCapture?.();
        },
        click: (e) => {
          if (e.target !== e.currentTarget) return;
          this.enterCodelineCapture?.();
        },
      });

    $(this.config.main)
      .find("li.codeline")
      .each((_, codeline) => this.updateAriaInfo(codeline, false))
      .on({
        focus: (event) => {
          if (this.codelineCaptureActive) {
            this.enterBlankOnCodelineFocus = true;
          }
          this.updateAriaInfo(event.currentTarget);
        },
        blur: (event) => {
          this.setCodelineInMotion(event.currentTarget, false);
          const nextFocus = event.relatedTarget;
          const staysInCodeArea =
            nextFocus &&
            ($(nextFocus).closest("li.codeline").exists() ||
              $(nextFocus).is("input.parsons-blank"));
          if (!staysInCodeArea) {
            this.exitCodelineCapture();
          }
          this.updateAriaInfo(event.currentTarget, false);
        },
        click: (e) => {
          if ($(e.target).is("input.parsons-blank")) return;
          this.enterBlankOnCodelineFocus = false;
          this.focusCodeline(e.currentTarget);
        },
        keyup: (e) => {
          const { moveCodeline } = getKeyMotionData(e);
          this.setCodelineInMotion(e.currentTarget, moveCodeline);
          this.updateAriaInfo(e.currentTarget);
        },
        keydown: (e) => {
          const handled = this.onCodelineKeydown(e, e.currentTarget);
          if (!handled) {
            this.updateAriaInfo(e.currentTarget);
          }
          this.storeStudentProgress();
        },
      })
      .each((_, codeline) =>
        this.findBlanksIn(codeline).on({
          focus: () => {
            this.enterBlankOnCodelineFocus = true;
            this.updateAriaInfo(codeline);
          },
          input: (e) => {
            this.autoSizeBlank(e.currentTarget);
            this.syncMissingBlankState(e.currentTarget);
            this.storeStudentProgress();
            this.config.onBlankUpdate(e, e.currentTarget);
          },
          keydown: (e) => {
            this.onBlankKeydown(e, codeline, e.currentTarget);
            this.storeStudentProgress();
          },
        }),
      );

    $(this.config.main)
      .find(".codeline-tray")
      .each((trayNumber, tray) =>
        $(tray)
          .find("li.codeline")
          .each((codelineNumber, codeline) => {
            if ($(codeline).attr("logging-id")) return;
            const codelineId = `${trayNumber}.${codelineNumber}`;
            $(codeline).attr("logging-id", codelineId);
            this.findBlanksIn(codeline).each((blankNumber, blank) => {
              $(blank).attr("logging-id", `${codelineId}.${blankNumber}`);
            });
          }),
      );

    this.findBlanksIn(this.config.main).on({
      input: (e) => {
        this.addLogEntry("editBlank", {
          value: $(e.target).val(),
          id: $(e.target).attr("logging-id"),
        });
      },
    });

    this.addLogEntry("problemOpened", {});
  }

  /////////////////////////////// MOTION HELPERS ////////////////////////////

  focusCodeline(codeline, firstBlankNotLast = true) {
    let target = $(codeline);
    if (!target.exists()) return;
    if (this.enterBlankOnCodelineFocus) {
      const blanks = this.findBlanksIn(target);
      const blank = firstBlankNotLast ? blanks.first() : blanks.last();
      target = blank.or(target);
    }
    target.focus();
  }

  findHorizontalTarget(codeline, searchTray) {
    const sourceIndex = $(codeline)
      .parent()
      .children()
      .filter((_, line) => !this.isSortablePlaceholder(line))
      .index(codeline);
    const targetLines = $(searchTray)
      .find("li.codeline")
      .filter((_, line) => !this.isSortablePlaceholder(line));
    const target =
      sourceIndex < targetLines.length
        ? targetLines.eq(sourceIndex)
        : targetLines.last();

    return { found: target.exists(), target };
  }

  moveHorizontally(codeline, { moveForward, moveCodeline }) {
    const codeboxes = $(this.config.main).find(".codeline-tray");
    const m = codeboxes.length;
    if (m < 2) return;
    const codeboxIdx = codeboxes
      .toArray()
      .findIndex((c) => $(c).has(codeline).exists());
    const k = codeboxIdx + (moveForward ? +1 : -1);
    if (k < 0 || m <= k) return;
    const newTray = codeboxes.eq(k).find(".codeline-list");

    const { found, target } = this.findHorizontalTarget(codeline, newTray);

    if (!moveCodeline) {
      this.focusCodeline(target, moveForward);
      return;
    }

    const selection = $(document.activeElement).or(codeline);

    if (found) {
      $(codeline).insertBefore(target);
    } else {
      $(newTray).append(codeline);
    }

    $(selection).focus();
  }

  moveCursorInBlankHorizontally(e, codeline, blankIdx, { moveForward }) {
    const codelineBlanks = this.findBlanksIn(codeline);
    const blank = codelineBlanks.get(blankIdx);
    if (blank.selectionEnd != blank.selectionStart) return false;

    const cursorIdx = blank.selectionStart;
    const [lastTextIdx, lastBlankIdx, blankDelta] = moveForward
      ? [blank.value.length, codelineBlanks.length - 1, +1]
      : [0, 0, -1];

    if (cursorIdx != lastTextIdx) return false;

    e.preventDefault();

    if (blankIdx == lastBlankIdx) {
      this.moveHorizontally(codeline, { moveForward, moveCodeline: false });
    } else {
      codelineBlanks
        .eq(blankIdx + blankDelta)
        .each((_, input) => {
          const l = moveForward ? 0 : input.value.length;
          input.setSelectionRange(l, l);
        })
        .focus();
    }
    return true;
  }

  jumpToNextBlank(blank, { jumpForward }) {
    const delta = jumpForward ? +1 : -1;
    const allBlanks = this.findBlanksIn(this.config.main);
    const m = allBlanks.length;
    const nextIndex = (allBlanks.index(blank) + m + delta) % m;
    allBlanks.eq(nextIndex).focus();
  }

  moveVertically(codeline, { moveForward, moveToEnd, moveCodeline }) {
    const parent = $(codeline).parent();
    const nextChild = moveForward ? $(codeline).next() : $(codeline).prev();

    if (!nextChild.exists()) return;

    if (!moveCodeline) {
      const children = parent.children();
      const extremeChild = moveForward ? children.last() : children.first();
      this.focusCodeline(moveToEnd ? extremeChild : nextChild);
      return;
    }

    const selection = $(document.activeElement).or(codeline);

    if (moveToEnd) {
      if (moveForward) {
        parent.append(codeline);
      } else {
        parent.prepend(codeline);
      }
    } else if (moveForward) {
      nextChild.insertBefore(codeline);
    } else {
      nextChild.insertAfter(codeline);
    }

    $(selection).focus();
  }

  onCodelineKeydown(e, codeline) {
    const motionData = getKeyMotionData(e);
    this.setCodelineInMotion?.(codeline, motionData.moveCodeline);

    if (!$(codeline).is(":focus")) return false;

    switch (e.key) {
      case "Tab":
        e.preventDefault();
        if (
          motionData.jumpForward &&
          $(this.config.starter).has(codeline).exists()
        ) {
          this.moveHorizontally(codeline, {
            moveForward: true,
            moveCodeline: true,
          });
        } else {
          const delta = motionData.jumpForward ? +1 : -1;
          this.updateIndent(codeline, delta, false);
        }
        return true;
      case "Enter":
        e.preventDefault();
        this.codelineCaptureActive = true;
        this.enterBlankOnCodelineFocus = true;
        this.findBlanksIn(codeline).first().focus();
        return true;
      case "Escape":
        e.preventDefault();
        this.exitCodelineCapture();
        return true;
      case "ArrowLeft":
      case "ArrowRight":
        e.preventDefault();
        this.moveHorizontally(codeline, motionData);
        return true;
      case "ArrowUp":
      case "ArrowDown":
        e.preventDefault();
        this.moveVertically(codeline, motionData);
        return true;
    }

    return false;
  }

  onBlankKeydown(e, codeline, blank) {
    const blanks = this.findBlanksIn(codeline);
    const blankIdx = blanks.index(blank);
    const motionData = getKeyMotionData(e);

    switch (e.key) {
      case "Tab": {
        const delta = motionData.jumpForward ? +1 : -1;
        e.preventDefault();
        this.updateIndent(codeline, delta, false);
        return;
      }
      case "Escape":
        e.preventDefault();
        e.stopPropagation();
        this.exitCodelineCapture();
        return;
      case "Enter":
        e.preventDefault();
        this.enterBlankOnCodelineFocus = true;
        this.jumpToNextBlank(blank, motionData);
        return;
      case "ArrowUp":
      case "ArrowDown":
        e.preventDefault();
        this.moveVertically(codeline, motionData);
        return;
      case "ArrowRight":
      case "ArrowLeft":
        if (motionData.moveCodeline) {
          e.preventDefault();
          this.moveHorizontally(codeline, motionData);
        } else {
          this.moveCursorInBlankHorizontally(e, codeline, blankIdx, motionData);
        }
        return;
    }
  }

  /////////////////////////////// GENERAL HELPERS ////////////////////////////

  clampIndent(indent) {
    return Math.max(0, Math.min(indent, this.config.maxIndentLevel));
  }

  getIndentAtDragPosition(ui) {
    const { item, position } = ui;
    const codeline = item[0];
    const tray = getCurrentDragTray(ui);
    const dragLeft = ui?.offset?.left ?? position?.left ?? 0;
    const trayLeft = getPageLeft(tray) ?? getPageLeft(item.parent()) ?? 0;
    const pxDelta = dragLeft - trayLeft;
    const charDelta = pxDelta / CHAR_WIDTH_IN_PX;
    const levelDelta = Math.floor(charDelta / this.config.xIndent);
    return this.clampIndent(this.getCodelineIndent(codeline) + levelDelta);
  }

  syncSortablePlaceholder(codeline, indent) {
    if (indent === undefined) {
      indent = this.getCodelineIndent(codeline);
    }
    const placeholder = this.activeSortablePlaceholder;
    if (!placeholder || !placeholder.exists()) return;

    placeholder.empty().css("--pl-faded-parsons-indent", indent);
  }

  /** Returns the indentation level of the codeline */
  getCodelineIndent(codeline) {
    codeline = $(codeline).get(0);
    const logicalIndent = parseInt(
      codeline.style &&
        codeline.style.getPropertyValue("--pl-faded-parsons-indent"),
      10,
    );
    if (!isNaN(logicalIndent)) return logicalIndent;

    // Fallback for older markup that still stores a visual margin-left.
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
    // this schema is used in pl-faded-parsons.py `Line.from_pl_data`
    return {
      codeSnippets: elemClone.text().split("!BLANK"),
      blankValues: blankValues,
    };
  }

  generateMockPLData() {
    const txInputs = [$(this.config.storage), $(this.config.logStorage)];
    const data = {};
    for (let inp of txInputs) {
      data[inp.attr("name")] = inp.val();
    }
    return JSON.stringify({ raw_submitted_answers: data });
  }

  autoSizeBlank(el) {
    $(el).width(el.value.length.toString() + "ch");
  }

  syncMissingBlankState(el) {
    const blank = $(el);
    const missing = !((el && el.value) || "").trim();
    blank
      .toggleClass("parsons-blank-missing", missing)
      .attr("aria-invalid", missing ? "true" : null);
  }

  getSourceLines() {
    return $(this.config.starterList)
      .children()
      .filter((_, line) => !this.isSortablePlaceholder(line))
      .toArray();
  }

  getSolutionLines() {
    return $(this.config.solutionList)
      .children()
      .filter((_, line) => !this.isSortablePlaceholder(line))
      .toArray();
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
          this.getCodelineSegments(line).codeSnippets.join("BLANK"),
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
      ? "// "
      : "# ";
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
    newCodeIndent = this.clampIndent(newCodeIndent);

    if (oldCodeIndent == newCodeIndent) return oldCodeIndent;

    this.config.onSortableUpdate(
      {
        type: "reindent",
        content: this.getCodelineText(codeline),
        old: oldCodeIndent,
        new: newCodeIndent,
      },
      this.getSolutionLines(),
    );

    $(codeline).css("--pl-faded-parsons-indent", newCodeIndent);

    this.updateAriaInfo(codeline);
    this.storeStudentProgress();
    return newCodeIndent;
  }

  storeStudentProgress() {
    // this schema is used in pl-faded-parsons.py `ProblemState.from_pl_data`!
    const storage = $(this.config.storage);
    if (!storage.exists()) {
      alert("Could not save student data!");
      return;
    }

    const pythonSummary = (line) => ({
      indent: this.getCodelineIndent(line),
      ...this.getCodelineSegments(line),
    });

    storage.val(
      JSON.stringify({
        starter: this.getSourceLines().map(pythonSummary),
        solution: this.getSolutionLines().map(pythonSummary),
      }),
    );
  }

  toggleDarkmode() {
    $(this.config.main)
      .find(PRETTIFY_OUTPUT_CLASSES)
      .add($(this.config.main))
      .each((_, e) => $(e).toggleClass("dark"));
  }

  updateAriaInfo(codeline, hasFocus = true) {
    const defaultText =
      "No code-line selected. Press Enter on the widget to focus the first code-line. Code-lines and blanks stay out of the tab order until you activate the widget. Press Escape to return focus to the widget. ";

    $(this.config.ariaDescriptor).text(
      hasFocus ? this.codelineAriaDescription(codeline) : defaultText,
    );

    $(this.config.ariaDetails).text(
      hasFocus
        ? this.codelineAriaDetails(codeline)
        : defaultText +
            "Use arrow keys to navigate, option or alt with arrow keys to move code-lines, tab and shift tab to indent, and enter to focus the code-lines." +
            "use shift to reverse motion, and option/ctrl to jump.",
    );
  }

  /////////////////////////////// ACCESSIBILITY HELPERS ////////////////////////////

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
        if (this.isSortablePlaceholder(sib)) return false;
        const sibIndentLevel = this.getCodelineIndent(sib);
        const sibDedented = sibIndentLevel < indentLevel;
        indentLevel = Math.min(sibIndentLevel, indentLevel);
        return sibDedented;
      })
      .toArray();
    return (
      [codeline, ...visualDedentParents]
        .map((cl) => this.codelineAriaDescription(cl))
        .join("; Under ") +
      trayText +
      " Press escape to return to the widget."
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

  /////////////////////////////// LOGGING HELPERS ////////////////////////////

  codelineLogEntry(line) {
    return {
      indent: this.getCodelineIndent(line),
      segments: this.getCodelineSegments(line),
      id: $(line).attr("logging-id"),
      index: line.index(),
    };
  }

  /** Add a tagged, timestamped log entry to `this.config.logStorage` */
  addLogEntry(tag, data) {
    if (!this.config.loggingEnabled) return;

    const timestamp = new Date();

    const entry = { timestamp, tag, data };

    const s = $(this.config.logStorage).expectExists("log storage");

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

/** Only used in unit tests -- do not delete! */
window.ParsonsWidgetHelpers = {
  buildWidgetConfig,
  buildToolbarHelpContent,
  getKeyMotionData,
  getCurrentDragTray,
  rememberDragStartTray,
  forgetDragStartTray,
  draggedFromAnotherTray,
  landedInAnotherTray,
};
window.ParsonsWidget = ParsonsWidget;
