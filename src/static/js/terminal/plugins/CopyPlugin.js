import { TerminalModule } from "../pipeline/TerminalModule.js";

export class CopyPlugin extends TerminalModule {
  constructor() {
    super("CopyPlugin", 90); // High priority to intercept keystrokes
  }

  setup(terminal, tab) {
    this.terminal = terminal;
  }

  inputNeedsProcess(event, context) {
    if (event.type === "copy") return true;

    if (event.type === "keydown") {
      // Handle Ctrl-Shift-C
      if (
        event.ctrlKey &&
        event.shiftKey &&
        (event.key === "c" || event.key === "C" || event.code === "KeyC")
      ) {
        return true;
      }

      // Handle context-aware Ctrl-C
      // If user presses Ctrl-C AND text is selected, we want to copy instead of SIGINT
      if (
        event.ctrlKey &&
        !event.shiftKey &&
        !event.altKey &&
        (event.key === "c" || event.key === "C" || event.code === "KeyC") &&
        context.state.hasSelection
      ) {
        return true;
      }
    }
    return false;
  }

  processInput(event, context) {
    if (event.type === "copy") {
      const selection = context.api.getSelection();
      if (selection) {
        event.originalEvent.clipboardData.setData(
          "text/plain",
          globalThis.filterTerminalFluff
            ? globalThis.filterTerminalFluff(selection)
            : selection,
        );
        event.originalEvent.preventDefault();
      }
      return true;
    }

    const selection = context.api.getSelection();
    if (selection) {
      navigator.clipboard
        .writeText(
          globalThis.filterTerminalFluff
            ? globalThis.filterTerminalFluff(selection)
            : selection,
        )
        .catch((err) => console.error("Copy failed", err));
      context.api.clearSelection();
    } else {
      document.execCommand("copy");
    }
    return true; // Consume event
  }
}
