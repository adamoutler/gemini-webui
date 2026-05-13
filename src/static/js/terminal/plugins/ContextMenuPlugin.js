import { TerminalModule } from "../pipeline/TerminalModule.js";
import { showDesktopContextMenu } from "../../ui/contextMenu.js";

export class ContextMenuPlugin extends TerminalModule {
  constructor() {
    super("ContextMenuPlugin", 70);
  }

  setup(terminal, tab) {
    this.terminal = terminal;
    this.tab = tab;
  }

  inputNeedsProcess(event, context) {
    if (context.state.isMobile) return false; // Mobile has its own context menu logic currently

    if (event.type === "contextmenu") return true;
    return false;
  }

  processInput(event, context) {
    const e = event.originalEvent;

    // Prevent default right-click menu
    const isInput =
      e.target.tagName === "INPUT" ||
      e.target.tagName === "TEXTAREA" ||
      e.target.isContentEditable;

    if (isInput) return false;

    let el = e.target;
    let allowMenu = false;
    while (el) {
      if (el.classList && el.classList.contains("xterm-cursor-layer")) {
        allowMenu = true;
        break;
      }
      if (
        el.id === "terminal-container" ||
        el.id === "tabs-container" ||
        el.tagName === "A" ||
        el.tagName === "BUTTON"
      ) {
        allowMenu = true;
        break;
      }
      el = el.parentElement;
    }

    if (!allowMenu) {
      e.preventDefault();
      return true;
    }

    e.preventDefault();
    showDesktopContextMenu(e.pageX, e.pageY);

    return true; // Consume event
  }
}
