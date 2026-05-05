export class InputRule {
  handleEvent(event, context) {
    return false; // Return true to prevent default processing
  }
}

export class ExtensionRuleParser {
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

export class CursorPlacementRule extends InputRule {
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

export class BackspaceRule extends InputRule {
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

export class ModifierRule extends InputRule {
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
            const code = char.codePointAt(0);
            if (code >= 97 && code <= 122)
              char = String.fromCodePoint(code - 96);
            else if (code >= 65 && code <= 90)
              char = String.fromCodePoint(code - 64);
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

export class WordBoundaryRule extends InputRule {
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
      const isDeletion =
        event.inputType === "deleteContentBackward" ||
        event.inputType === "deleteWordBackward";

      if (isDictation || isComposing || isDeletion) {
        return false;
      }

      if (this.boundaryRegex.test(input.value)) {
        if (input.value === " ") {
          if (!context.canDoubleSpacePeriod) {
            context.emitToTerminal(" ");
            input.value = "";
            return true;
          }
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
