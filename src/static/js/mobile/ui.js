export class MobileInputBuffer {
  constructor(emitCallback, isMobile, modifierState) {
    this.emitCallback = emitCallback;
    this.isMobile = isMobile;
    this.modifierState = modifierState;
  }

  handleInput(
    e,
    isComposing,
    value,
    forceEmit = false,
    lastValue = "",
    isDictation = false,
  ) {
    if (
      e.inputType === "deleteContentBackward" ||
      e.inputType === "deleteWordBackward"
    ) {
      if (!this.isMobile) return undefined;
      // If the buffer was ALREADY empty before this delete event,
      // it means the user pressed backspace on an empty buffer.
      if (lastValue.length === 0) {
        this.emitCallback("\x7f");
        return ""; // Force clear
      }
      return undefined; // Let normal backspace delete characters from the proxy buffer
    }

    // If modifiers are active, consume exactly 1 char from data, apply modifiers, emit, clear buffer
    if (
      this.modifierState &&
      (this.modifierState.ctrlActive ||
        this.modifierState.altActive ||
        this.modifierState.shiftActive ||
        this.modifierState.superActive)
    ) {
      const char =
        e.data && e.data.length > 0
          ? e.data[e.data.length - 1]
          : value
            ? value.slice(-1)
            : null;
      if (char) {
        const modified = this.modifierState.applyModifiers(char);
        this.emitCallback(modified);
        // Return the buffer without the consumed character
        return value.slice(0, -1);
      }
    }

    const boundaryRegex = /[\s.,?!;—，。？！；]/; // Match boundary ANYWHERE

    // If it's dictation or active composition (voice typing/swipe), don't clear on every space.
    // Let the compositionend event or dictationTimer force the flush.
    if ((isDictation || isComposing) && !forceEmit) {
      return undefined;
    }

    // For normal typing, if we hit a boundary or it's forced, emit the whole value and clear.
    if (
      forceEmit ||
      boundaryRegex.test(value) ||
      (!this.isMobile && value.length > 1)
    ) {
      this.emitCallback(value);
      return ""; // Synchronously clear the buffer
    }

    return undefined; // Keep buffering the current word
  }

  handleKeyDown(e, value, isComposing) {
    const passthroughKeys = {
      Tab: "\t",
      Escape: "\x1b",
    };

    // If it's an explicit control key, process it even if composing.
    if (passthroughKeys[e.key]) {
      e.preventDefault();
      let input = passthroughKeys[e.key];
      if (
        e.key === "Tab" &&
        (e.shiftKey || (this.modifierState && this.modifierState.shiftActive))
      ) {
        input = "\x1b[Z";
        if (this.modifierState && this.modifierState.shiftActive) {
          this.modifierState.toggleShift(false);
        }
      }
      if (e.key === "Escape") {
        this.emitCallback(input);
        return ""; // clear buffer
      } else {
        // Tab completely bypasses buffer, but does not clear it
        this.emitCallback(input);
        return undefined; // leave buffer intact
      }
    }

    if (e.altKey || e.ctrlKey || e.metaKey) {
      if (e.key && e.key.length === 1 && !e.metaKey) {
        e.preventDefault();
        let input = e.key;
        if (e.ctrlKey) {
          const code = input.codePointAt(0);
          if (code >= 97 && code <= 122)
            input = String.fromCodePoint(code - 96);
          else if (code >= 65 && code <= 90)
            input = String.fromCodePoint(code - 64);
        }
        if (e.altKey) {
          input = "\x1b" + input;
        }
        this.emitCallback(input);
        return ""; // Ctrl/Alt clear buffer
      }
      if (!this.isMobile) return "";
      return undefined;
    }

    if (isComposing) return undefined;

    if (e.key === "Backspace" || e.keyCode === 8) {
      if (value.length === 0) {
        if (!this.isMobile) return undefined;
        e.preventDefault();
        this.emitCallback("\x7f");
      }
    }
    if (e.key === "Enter") {
      if (!this.isMobile) return undefined;
      e.preventDefault();
      this.emitCallback(value + "\r");
      return "";
    }
    return undefined;
  }
}

export class MobileInputUI {
  constructor(tabId, inputHandler, keyDownHandler, ruleParser = null) {
    this.tabId = tabId;
    this.ruleParser = ruleParser;
    let container = document.getElementById("mobile-input-container");
    if (!container) {
      container = document.createElement("div");
      container.id = "mobile-input-container";
      container.className = "mobile-input-container";
      const mobileControls = document.getElementById("mobile-controls");
      if (mobileControls?.parentNode) {
        mobileControls.parentNode.insertBefore(container, mobileControls);
      } else {
        document.body.appendChild(container);
      }
    }

    let oldProxy = document.getElementById("terminal-input-mobile-" + tabId);
    if (oldProxy) oldProxy.remove();

    this.proxyInput = document.createElement("textarea");
    this.proxyInput.id = "terminal-input-mobile-" + tabId;
    this.proxyInput.className = "mobile-text-area";
    this.proxyInput.placeholder = "";
    this.proxyInput.setAttribute("inputmode", "text");

    // Make it visible, transparent background, positioned at cursor
    this.proxyInput.style.position = "absolute";
    this.proxyInput.style.opacity = "1";
    this.proxyInput.style.zIndex = "100";
    this.proxyInput.style.height = "2em"; // Enough for one line
    this.proxyInput.style.whiteSpace = "pre-wrap";
    this.proxyInput.style.wordBreak = "break-word";
    this.proxyInput.style.background = "transparent";
    this.proxyInput.style.color = "inherit";

    this.proxyInput.setAttribute("autocomplete", "on");
    this.proxyInput.setAttribute("autocorrect", "on");
    this.proxyInput.setAttribute("spellcheck", "true");
    this.proxyInput.setAttribute("autocapitalize", "none");

    container.appendChild(this.proxyInput);
    this.isComposing = false;
    this.proxyInput.addEventListener("compositionstart", (e) => {
      if (this.ruleParser && this.ruleParser.process(e)) return;
      this.isComposing = true;
      this.proxyInput.classList.add("is-composing");
    });
    let lastValue = this.proxyInput.value;

    this.proxyInput.addEventListener("compositionend", (e) => {
      if (this.ruleParser && this.ruleParser.process(e)) return;
      this.isComposing = false;
      this.proxyInput.classList.remove("is-composing");
      // Give the native input event a moment to fire and settle,
      // then flush the buffer to terminal if it's not empty.
      setTimeout(() => {
        if (this.proxyInput.value.length > 0) {
          // Send whatever was composed and clear the proxy
          inputHandler(
            { data: "" },
            false,
            this.proxyInput.value,
            true,
            lastValue,
          );
          this.proxyInput.value = "";
          lastValue = "";
        }
      }, 50);
    });

    this.proxyInput.addEventListener("beforeinput", (e) => {
      if (this.ruleParser && this.ruleParser.process(e)) {
        e.preventDefault();
      }
    });

    document.addEventListener("selectionchange", (e) => {
      if (document.activeElement === this.proxyInput) {
        if (this.ruleParser && this.ruleParser.process(e)) return;
      }
    });

    this.proxyInput.addEventListener("input", (e) => {
      if (this.ruleParser && this.ruleParser.process(e)) return;
      const currentValue = this.proxyInput.value;
      const isDictation = e.inputType === "insertDictationResult";

      // Voice typing can sometimes bypass compositionend, leaving us stuck in composing state
      if (
        (isDictation || e.inputType === "insertText") &&
        this.isComposing &&
        !e.isComposing
      ) {
        this.isComposing = false;
        this.proxyInput.classList.remove("is-composing");
      }

      const newValue = inputHandler(
        e,
        this.isComposing,
        currentValue,
        false,
        lastValue,
        isDictation,
      );
      if (newValue !== undefined) {
        this.proxyInput.value = newValue;
      }
      lastValue = this.proxyInput.value;

      // Auto-commit buffer after pause for dictation
      if (this.dictationTimer) {
        clearTimeout(this.dictationTimer);
        this.dictationTimer = null;
      }

      if (this.proxyInput.value.length > 0 && isDictation) {
        this.dictationTimer = setTimeout(() => {
          if (this.proxyInput.value.length > 0) {
            // Context-aware spacing: check terminal buffer
            let prefix = "";
            if (this.ruleParser && this.ruleParser.context.term) {
              const term = this.ruleParser.context.term;
              const buffer = term.buffer.active;
              const line = buffer.getLine(buffer.baseY + buffer.cursorY);
              const lastChar = line
                ? line.translateToString(
                    false,
                    buffer.cursorX - 1,
                    buffer.cursorX,
                  )
                : "";
              if (lastChar && lastChar !== " " && lastChar !== "\n") {
                prefix = " ";
              }
            }

            // Append a space to the end of the dictation result if it doesn't have one
            let text = this.proxyInput.value;
            if (!text.endsWith(" ")) {
              text += " ";
            }
            // force flush
            inputHandler(
              { data: "" },
              false,
              prefix + text,
              true,
              this.proxyInput.value,
              true,
            );
            this.proxyInput.value = "";
            lastValue = "";
          }
        }, 1500); // Increased from 800ms to 1500ms to reduce UI pressure during long dictation
      }
    });
    this.proxyInput.addEventListener("keydown", (e) => {
      if (this.ruleParser && this.ruleParser.process(e)) return;
      // If we press Enter and the browser left us stuck in a composing state after voice dictation, force clear it.
      if (e.key === "Enter" && this.isComposing && !e.isComposing) {
        this.isComposing = false;
        this.proxyInput.classList.remove("is-composing");
      }

      const newValue = keyDownHandler(
        e,
        this.proxyInput.value,
        this.isComposing,
      );
      if (newValue !== undefined) this.proxyInput.value = newValue;
    });
  }

  alignWithCursor(term) {
    if (!term || !this.proxyInput) return;
    if (globalThis.activeTabId && globalThis.activeTabId !== this.tabId) {
      this.proxyInput.style.display = "none";
      return;
    }
    this.proxyInput.style.display = "block";

    requestAnimationFrame(() => {
      let left = 0;
      let top = 0;
      let foundCursor = false;

      // First try the DOM cursor (if DOM renderer is used or cursor is blinking)
      const cursor = term.element.querySelector(".xterm-cursor");
      if (cursor) {
        const rect = cursor.getBoundingClientRect();
        if (rect.width > 0 && rect.height > 0) {
          left = rect.left;
          top = rect.top;
          foundCursor = true;
        }
      }

      // Fallback for WebGL/Canvas renderer where .xterm-cursor is hidden or non-existent
      let cellW = 9;
      let cellH = 17;
      try {
        if (
          !foundCursor &&
          term._core &&
          term._core._renderService &&
          term._core._renderService.dimensions
        ) {
          const dims = term._core._renderService.dimensions;
          cellW = dims.css?.cell?.width || dims.actualCellWidth || 9;
          cellH = dims.css?.cell?.height || dims.actualCellHeight || 17;

          const screenEl =
            term.element.querySelector(".xterm-screen") || term.element;
          const screenRect = screenEl.getBoundingClientRect();

          const cursorX = term.buffer.active.cursorX;
          const cursorY = term.buffer.active.cursorY;

          // Account for scroll offset
          const viewportY = term.buffer.active.viewportY;
          const baseY = term.buffer.active.baseY;
          const scrollOffsetLines = baseY - viewportY;
          const visualCursorY = cursorY + scrollOffsetLines;

          left = screenRect.left + cursorX * cellW;
          top = screenRect.top + visualCursorY * cellH;
          foundCursor = true;
        } else if (
          foundCursor &&
          term._core &&
          term._core._renderService &&
          term._core._renderService.dimensions
        ) {
          const dims = term._core._renderService.dimensions;
          cellW = dims.css?.cell?.width || dims.actualCellWidth || 9;
          cellH = dims.css?.cell?.height || dims.actualCellHeight || 17;
        }
      } catch (e) { console.debug("Ignored error:", e); }

      if (foundCursor) {
        let proxyLeft = left + cellW;
        if (proxyLeft >= globalThis.innerWidth - 10) {
          proxyLeft = globalThis.innerWidth - 10;
        }
        const remainingWidth = Math.max(globalThis.innerWidth - proxyLeft, 10);

        this.proxyInput.style.left = `${proxyLeft}px`;
        this.proxyInput.style.top = `${top - cellH / 3}px`;
        this.proxyInput.style.width = `${remainingWidth}px`;

        // Match terminal font metrics if possible
        const termEl = term.element.querySelector(".xterm-rows");
        if (termEl) {
          const style = globalThis.getComputedStyle(termEl);
          this.proxyInput.style.fontFamily = style.fontFamily;

          // Browsers inflate textarea font sizes sometimes. We explicitly set it exactly.
          const fontSizeStr = style.fontSize;
          this.proxyInput.style.setProperty(
            "font-size",
            fontSizeStr,
            "important",
          );

          this.proxyInput.style.lineHeight = style.lineHeight;
          this.proxyInput.style.letterSpacing = style.letterSpacing;
          this.proxyInput.style.color = style.color; // Explicitly inherit color
          this.proxyInput.style.caretColor = style.color;

          // Find background color to cover the underlying xterm cursor
          const bgStyle = globalThis.getComputedStyle(
            term.element.querySelector(".xterm-viewport") || term.element,
          );
          const termBg =
            bgStyle.backgroundColor !== "rgba(0, 0, 0, 0)"
              ? bgStyle.backgroundColor
              : "var(--bg-primary, #1e1e1e)";

          this.proxyInput.style.backgroundColor = termBg;

          // Create a fake block cursor (bottom 25% of the first character cell)
          this.proxyInput.style.backgroundImage = `linear-gradient(to bottom, transparent 75%, #414141 75%)`;
          this.proxyInput.style.backgroundSize = `${cellW}px 100%`;
          this.proxyInput.style.backgroundRepeat = "no-repeat";
        }
      }
    });
  }
}
