class InputRule {
  handleEvent(event, context) {
    return false; // Return true to prevent default processing
  }
}

class ExtensionRuleParser {
  constructor(context) {
    this.rules = [];
    this.context = context; // { ui, emitToTerminal, getProxyInput }
  }

  registerRule(rule) {
    this.rules.push(rule);
  }

  process(event) {
    for (const rule of this.rules) {
      if (rule.handleEvent(event, this.context)) {
        return true;
      }
    }
    return false;
  }
}

class CursorPlacementRule extends InputRule {
  constructor() {
    super();
    this.lastSelectionStart = 0;
    this.lastValue = "";
    this.lastEventTime = 0;
  }

  handleEvent(event, context) {
    const input = context.getProxyInput();
    if (!input) return false;

    if (event.type === "selectionchange" && document.activeElement === input) {
      const currentStart = input.selectionStart;
      const currentValue = input.value;
      const now = Date.now();

      // If value hasn't changed and it's not immediately after an input event
      if (
        this.lastSelectionStart !== null &&
        currentValue === this.lastValue &&
        currentStart !== this.lastSelectionStart &&
        now - this.lastEventTime > 50
      ) {
        const diff = currentStart - this.lastSelectionStart;
        if (diff > 0) {
          for (let i = 0; i < diff; i++) context.emitToTerminal("\x1b[C");
        } else if (diff < 0) {
          for (let i = 0; i < -diff; i++) context.emitToTerminal("\x1b[D");
        }
      }
      this.lastSelectionStart = currentStart;
      this.lastValue = currentValue;
      return false; // let other selection logic run if any
    }

    if (event.type === "input" || event.type === "keydown") {
      this.lastEventTime = Date.now();
      setTimeout(() => {
        if (input) {
          this.lastSelectionStart = input.selectionStart;
          this.lastValue = input.value;
        }
      }, 0);
    }
    return false;
  }
}

class BackspaceRule extends InputRule {
  constructor() {
    super();
    this.lastValue = "";
  }
  handleEvent(event, context) {
    const input = context.getProxyInput();
    if (!input) return false;

    if (event.type === "keydown") {
      this.lastValue = input.value;
      if (event.key === "Backspace" || event.keyCode === 8) {
        context.canDoubleSpacePeriod = false;
        if (input.value.length === 0) {
          event.preventDefault();
          context.emitToTerminal("\x7f");
          return true;
        }
      }
    }

    if (event.type === "input") {
      if (
        event.inputType === "deleteContentBackward" ||
        event.inputType === "deleteWordBackward"
      ) {
        context.canDoubleSpacePeriod = false;
        if (this.lastValue.length === 0) {
          context.emitToTerminal("\x7f");
          input.value = "";
          return true;
        }
      }
      this.lastValue = input.value;
    }
    return false;
  }
}

class ModifierRule extends InputRule {
  handleEvent(event, context) {
    const input = context.getProxyInput();
    const modifierState = context.modifierState;
    const isComposing = context.ui && context.ui.isComposing;

    if (event.type === "keydown") {
      if (event.altKey || event.ctrlKey || event.metaKey) {
        if (event.key && event.key.length === 1 && !event.metaKey) {
          event.preventDefault();
          let char = event.key;
          if (event.ctrlKey) {
            const code = char.charCodeAt(0);
            if (code >= 97 && code <= 122)
              char = String.fromCharCode(code - 96);
            else if (code >= 65 && code <= 90)
              char = String.fromCharCode(code - 64);
            else if (code === 32) char = "\x00";
            else if (code === 91) char = "\x1b";
            else if (code === 92) char = "\x1c";
            else if (code === 93) char = "\x1d";
          }
          if (event.altKey) {
            char = "\x1b" + char;
          }
          if (input && input.value.length > 0) {
            context.emitToTerminal(input.value);
            input.value = "";
          }
          context.emitToTerminal(char);
          return true;
        } else if (event.key === "Enter" && (event.altKey || event.ctrlKey)) {
          event.preventDefault();
          if (input) {
            input.value += "\n";
            // Trigger input event to update any observers/proxies
            input.dispatchEvent(new Event("input", { bubbles: true }));
          }
          return true;
        }
      }
    }

    if (
      event.type === "input" &&
      modifierState &&
      (modifierState.ctrlActive ||
        modifierState.altActive ||
        modifierState.shiftActive ||
        modifierState.superActive)
    ) {
      if (isComposing) return false;
      const char =
        event.data && event.data.length > 0
          ? event.data[event.data.length - 1]
          : input && input.value
            ? input.value.slice(-1)
            : null;
      if (char) {
        const modified = modifierState.applyModifiers(char);
        context.emitToTerminal(modified);
        if (input) input.value = input.value.slice(0, -1);
        return true;
      }
    }

    return false;
  }
}

class WordBoundaryRule extends InputRule {
  constructor() {
    super();
    this.boundaryRegex = /[\s.,?!;\-—，。？！；]/;
  }
  handleEvent(event, context) {
    if (event.type === "input") {
      const input = context.getProxyInput();
      if (!input) return false;

      const isDictation = event.inputType === "insertDictationResult";
      const isComposing = context.ui && context.ui.isComposing;

      if (isDictation || isComposing) {
        return false;
      }

      if (this.boundaryRegex.test(input.value)) {
        if (input.value === " ") {
          return true;
        }

        if (input.value === "  ") {
          if (context.canDoubleSpacePeriod) {
            // Emit period and space to replace the two spaces in the proxy buffer
            context.emitToTerminal(".\x20");
            input.value = "";
            context.canDoubleSpacePeriod = false;
            return true;
          }
        }

        let toEmit = input.value;
        let toKeep = "";

        if (input.value.endsWith(" ")) {
          toEmit = input.value.slice(0, -1);
          toKeep = " ";
        } else {
          // Find the last sequence of boundaries and split there
          const match = input.value.match(
            /([\s.,?!;\-—，。？！；]+)([^[\s.,?!;\-—，。？！；]*)$/,
          );
          if (match) {
            const boundaryEndIndex = input.value.length - match[2].length;
            toEmit = input.value.substring(0, boundaryEndIndex);
            toKeep = match[2];
          }
        }

        if (toEmit) {
          context.emitToTerminal(toEmit);
          // If the emitted text doesn't end with a boundary, a double-space can trigger a period.
          context.canDoubleSpacePeriod = !this.boundaryRegex.test(
            toEmit.slice(-1),
          );
        }
        input.value = toKeep;
        return true;
      }
    } else if (event.type === "keydown" && event.key === "Enter") {
      const isComposing = context.ui && context.ui.isComposing;
      if (isComposing) return false;

      const input = context.getProxyInput();
      if (input) {
        event.preventDefault();
        context.emitToTerminal(input.value + "\r");
        input.value = "";
        return true;
      }
    }
    return false;
  }
}

class MobileModifierState {
  static instance = null;

  constructor() {
    if (MobileModifierState.instance) {
      return MobileModifierState.instance;
    }

    this.ctrlActive = false;
    this.altActive = false;
    this.shiftActive = false;
    this.superActive = false;

    // Clone and replace buttons to strip old event listeners from previous connections
    const replaceBtn = (id) => {
      const btn = document.getElementById(id);
      if (!btn) return null;
      const newBtn = btn.cloneNode(true);
      btn.parentNode.replaceChild(newBtn, btn);
      return newBtn;
    };

    this.ctrlBtn = replaceBtn("ctrl-toggle");
    this.altBtn = replaceBtn("alt-toggle");
    this.shiftBtn = replaceBtn("shift-toggle");
    this.superBtn = replaceBtn("super-toggle");

    // Reset visual state on recreation
    if (this.ctrlBtn) this.ctrlBtn.classList.remove("active");
    if (this.altBtn) this.altBtn.classList.remove("active");
    if (this.shiftBtn) this.shiftBtn.classList.remove("active");
    if (this.superBtn) this.superBtn.classList.remove("active");

    this.setupListeners();
    MobileModifierState.instance = this;
  }
  setupListeners() {
    const bindBtn = (btn, toggleFn) => {
      if (!btn) return;
      const handler = (e) => {
        if (e.type === "touchstart" || e.type === "touchend") {
          e.preventDefault();
        }
        if (e.type === "touchstart" || e.type === "mousedown") {
          if (window.triggerHapticFeedback) window.triggerHapticFeedback();
          // Focus immediately on touchstart/mousedown to ensure keyboard pops up
          const activeProxy = document.querySelector(".mobile-text-area");
          if (activeProxy) {
            activeProxy.focus();
          }
        }
        if (e.type === "touchend" || e.type === "mousedown") {
          toggleFn();
          // Re-focus on touchend to be absolutely sure
          const activeProxy = document.querySelector(".mobile-text-area");
          if (activeProxy) {
            activeProxy.focus();
          }
        }
      };
      btn.addEventListener("touchstart", handler, { passive: false });
      btn.addEventListener("touchend", handler, { passive: false });
      btn.addEventListener("mousedown", handler);
    };
    bindBtn(this.ctrlBtn, () => this.toggleCtrl());
    bindBtn(this.altBtn, () => this.toggleAlt());
    bindBtn(this.shiftBtn, () => this.toggleShift());
    bindBtn(this.superBtn, () => this.toggleSuper());
  }

  toggleCtrl(force) {
    this.ctrlActive = force !== undefined ? force : !this.ctrlActive;
    if (this.ctrlBtn) {
      if (this.ctrlActive) this.ctrlBtn.classList.add("active");
      else this.ctrlBtn.classList.remove("active");
    }
  }

  toggleAlt(force) {
    this.altActive = force !== undefined ? force : !this.altActive;
    if (this.altBtn) {
      if (this.altActive) this.altBtn.classList.add("active");
      else this.altBtn.classList.remove("active");
    }
  }

  toggleShift(force) {
    this.shiftActive = force !== undefined ? force : !this.shiftActive;
    if (this.shiftBtn) {
      if (this.shiftActive) this.shiftBtn.classList.add("active");
      else this.shiftBtn.classList.remove("active");
    }
  }

  toggleSuper(force) {
    this.superActive = force !== undefined ? force : !this.superActive;
    if (this.superBtn) {
      if (this.superActive) this.superBtn.classList.add("active");
      else this.superBtn.classList.remove("active");
    }
  }

  applyModifiers(data) {
    if (!data) return data;
    let input = data;

    if (this.shiftActive && data === "\t") {
      input = "\x1b[Z";
      this.toggleShift(false);
      return input;
    }

    if (this.ctrlActive && data.length === 1) {
      const code = data.charCodeAt(0);
      if (code >= 97 && code <= 122) {
        // a-z
        input = String.fromCharCode(code - 96);
      } else if (code >= 65 && code <= 90) {
        // A-Z
        input = String.fromCharCode(code - 64);
      } else if (code === 32) {
        // Ctrl+Space
        input = "\x00";
      } else if (code === 91) {
        // Ctrl+[
        input = "\x1b";
      } else if (code === 92) {
        // Ctrl+\
        input = "\x1c";
      } else if (code === 93) {
        // Ctrl+]
        input = "\x1d";
      }
      this.toggleCtrl(false);
    } else if (this.ctrlActive) {
      this.toggleCtrl(false);
    }

    if (this.altActive && data.length === 1) {
      input = "\x1b" + input;
      this.toggleAlt(false);
    } else if (this.altActive) {
      this.toggleAlt(false);
    }

    if (this.superActive && data.length === 1) {
      // Super+key: send as Alt+key if it's a simple character,
      // as Gemini CLI supports Alt+Z for undo.
      input = "\x1b" + input;
      this.toggleSuper(false);
    } else if (this.superActive) {
      this.toggleSuper(false);
    }

    if (this.shiftActive && data.length === 1) {
      const code = data.charCodeAt(0);
      if (code >= 97 && code <= 122) {
        input = String.fromCharCode(code - 32);
      }
      this.toggleShift(false);
    } else if (this.shiftActive) {
      this.toggleShift(false);
    }

    return input;
  }
}

class MobileInputBuffer {
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
          const code = input.charCodeAt(0);
          if (code >= 97 && code <= 122) input = String.fromCharCode(code - 96);
          else if (code >= 65 && code <= 90)
            input = String.fromCharCode(code - 64);
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

class MobileInputUI {
  constructor(tabId, inputHandler, keyDownHandler, ruleParser = null) {
    this.tabId = tabId;
    this.ruleParser = ruleParser;
    let container = document.getElementById("mobile-input-container");
    if (!container) {
      container = document.createElement("div");
      container.id = "mobile-input-container";
      container.className = "mobile-input-container";
      const mobileControls = document.getElementById("mobile-controls");
      if (mobileControls && mobileControls.parentNode) {
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
    if (window.activeTabId && window.activeTabId !== this.tabId) {
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
      try {
        if (
          !foundCursor &&
          term._core &&
          term._core._renderService &&
          term._core._renderService.dimensions
        ) {
          const dims = term._core._renderService.dimensions;
          cellW = dims.css?.cell?.width || dims.actualCellWidth || 9;
          const cellH = dims.css?.cell?.height || dims.actualCellHeight || 17;

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
        }
      } catch (e) {}

      if (foundCursor) {
        let proxyLeft = left + cellW;
        if (proxyLeft >= window.innerWidth - 10) {
          proxyLeft = window.innerWidth - 10;
        }
        const remainingWidth = Math.max(window.innerWidth - proxyLeft, 10);

        this.proxyInput.style.left = `${proxyLeft}px`;
        this.proxyInput.style.top = `${top}px`;
        this.proxyInput.style.width = `${remainingWidth}px`;

        // Match terminal font metrics if possible
        const termEl = term.element.querySelector(".xterm-rows");
        if (termEl) {
          const style = window.getComputedStyle(termEl);
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
          const bgStyle = window.getComputedStyle(
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

class MobileTerminalController {
  constructor(tab) {
    this.tab = tab;

    this.isMobile = document.documentElement.classList.contains("is-mobile");

    if (this.isMobile) {
      this.modifierState = new MobileModifierState();

      this.ruleParser = new ExtensionRuleParser({
        emitToTerminal: this.emitToTerminal.bind(this),
        getProxyInput: () => (this.ui ? this.ui.proxyInput : null),
        modifierState: this.modifierState,
        term: tab.term,
      });
      this.ruleParser.registerRule(new CursorPlacementRule());
      this.ruleParser.registerRule(new BackspaceRule());
      this.ruleParser.registerRule(new ModifierRule());
      this.ruleParser.registerRule(new WordBoundaryRule());

      this.buffer = new MobileInputBuffer(
        this.emitToTerminal.bind(this),
        this.isMobile,
        this.modifierState,
      );
      this.ui = new MobileInputUI(
        this.tab.id,
        this.buffer.handleInput.bind(this.buffer),
        this.buffer.handleKeyDown.bind(this.buffer),
        this.ruleParser,
      );
      this.ruleParser.context.ui = this.ui;

      this.setupFocusManagement();
    }
  }

  setupFocusManagement() {
    if (!this.tab.term) return;

    // Disable xterm's native textarea on mobile so it cannot steal focus
    // and cause the mobile keyboard to flash on re-taps.
    const nativeTextarea = this.tab.term.textarea;
    if (nativeTextarea && this.isMobile) {
      nativeTextarea.disabled = true;
      nativeTextarea.style.display = "none";
    }
    // Handle paste directly on our proxy input since we disabled xterm's textarea
    this.ui.proxyInput.addEventListener("paste", async (e) => {
      const items = (e.clipboardData || window.clipboardData)?.items;
      let hasImage = false;
      if (items) {
        for (let i = 0; i < items.length; i++) {
          const item = items[i];
          if (item.type.startsWith("image/")) {
            hasImage = true;
            e.preventDefault();
            const file = item.getAsFile();
            if (!file) continue;

            if (typeof uploadPastedImage === "function") {
              await uploadPastedImage(
                file,
                this.tab,
                this.emitToTerminal.bind(this),
              );
            } else {
              this.emitToTerminal(
                `\r\n\x1b[31m[Error] uploadPastedImage function not available.\x1b[0m\r\n`,
              );
            }
          }
        }
      }

      if (hasImage) return;

      let pasteText = (e.clipboardData || window.clipboardData).getData("text");
      if (pasteText) {
        e.preventDefault();

        // Use bracketed paste if enabled by terminal
        const useBracketedPaste =
          this.tab.term &&
          this.tab.term.modes &&
          this.tab.term.modes.bracketedPasteMode;
        if (useBracketedPaste) {
          pasteText = "\x1b[200~" + pasteText + "\x1b[201~";
        }

        // Force flush the pasted text immediately
        const newValue = this.buffer.handleInput(
          { data: pasteText, inputType: "insertFromPaste" },
          false,
          this.ui.proxyInput.value + pasteText,
          true,
          this.ui.proxyInput.value,
          false,
        );
        if (newValue !== undefined) {
          this.ui.proxyInput.value = newValue;
        }
      }
    });
    // Use a click listener on the document to focus our proxy input if they tap anywhere.
    // A standard click event reliably detects a tap (vs a long-press/scroll).
    document.addEventListener("click", (e) => {
      if (!this.isMobile) return;
      // Do not steal focus if they clicked a button, link, or another input
      const target = e.target;
      const isInteractive = target.closest(
        "button, a, input, select, .control-btn, .header-icon",
      );
      if (!isInteractive && window.activeTabId === this.tab.id) {
        this.ui.proxyInput.focus();
        this.ui.alignWithCursor(this.tab.term);
      }
    });

    // Update alignment when cursor moves
    this.tab.term.onCursorMove(() => {
      this.ui.alignWithCursor(this.tab.term);
    });

    // Update alignment when proxy input changes (in case width/opacity needs changing)
    this.ui.proxyInput.addEventListener("input", () => {
      this.ui.alignWithCursor(this.tab.term);
    });

    // Re-align on terminal scroll
    const viewport = this.tab.term.element.querySelector(".xterm-viewport");
    if (viewport) {
      viewport.addEventListener("scroll", () => {
        this.ui.alignWithCursor(this.tab.term);
      });
    }

    // Re-align on resize or scroll
    window.addEventListener("resize", () =>
      this.ui.alignWithCursor(this.tab.term),
    );
    if (window.visualViewport) {
      window.visualViewport.addEventListener("resize", () =>
        this.ui.alignWithCursor(this.tab.term),
      );
      window.visualViewport.addEventListener("scroll", () =>
        this.ui.alignWithCursor(this.tab.term),
      );
    }
  }

  emitToTerminal(data) {
    const activeTab = window.tabs
      ? window.tabs.find((t) => t.id === window.activeTabId)
      : this.tab;
    const targetTab = activeTab || this.tab;

    if (!targetTab || !targetTab.socket || data == null) return;
    if (window.emitPtyInput) {
      window.emitPtyInput(targetTab, data);
    } else {
      const strData = String(data).replace(/\n/g, "\r");
      targetTab.socket.emit("pty-input", { input: strData });
    }
  }
}

if (typeof module !== "undefined" && module.exports) {
  module.exports = {
    InputRule,
    ExtensionRuleParser,
    MobileInputBuffer,
    MobileInputUI,
    MobileTerminalController,
    MobileModifierState,
    BackspaceRule,
    ModifierRule,
    WordBoundaryRule,
  };
}
