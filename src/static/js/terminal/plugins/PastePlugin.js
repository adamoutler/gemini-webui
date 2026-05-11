import { TerminalModule } from "../pipeline/TerminalModule.js";

export class PastePlugin extends TerminalModule {
  constructor() {
    super("PastePlugin", 80);
  }

  setup(terminal, tab) {
    this.terminal = terminal;
  }

  inputNeedsProcess(event, context) {
    if (event.type === "paste") return true;

    if (
      event.type === "keydown" &&
      event.ctrlKey &&
      event.shiftKey &&
      (event.key === "v" || event.key === "V" || event.code === "KeyV")
    ) {
      return true;
    }
    return false;
  }

  processInput(event, context) {
    // If it's a DOM paste event
    if (event.type === "paste") {
      // Image upload logic is handled in the UI/modals layer usually,
      // but text paste should be intercepted here.
      // We return false here if we want to let the existing document 'paste' listener handle it.
      // For now, since the user already has paste handlers mapped in `mobile-input-extra.js` or `ui.js`,
      // we might defer DOM pastes and just handle the explicit keyboard shortcut.
      if (event.originalEvent && event.originalEvent.clipboardData) {
        // If image paste, let other handlers do it or handle it here.
        // Returning false allows the existing global handlers to run.
        return false;
      }
    }

    // Handle Ctrl-Shift-V
    if (event.type === "keydown") {
      navigator.clipboard
        .readText()
        .then((text) => {
          if (text) {
            const useBracketedPaste =
              this.terminal &&
              this.terminal.modes &&
              this.terminal.modes.bracketedPasteMode;
            if (useBracketedPaste) {
              text = "\x1b[200~" + text + "\x1b[201~";
            }
            context.api.sendDataToServer(text);
          }
        })
        .catch((err) => console.error("Paste error", err));
      return true; // Consume
    }

    return false;
  }
}
