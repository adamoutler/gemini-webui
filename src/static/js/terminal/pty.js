import { globalState } from "../core/state.js";
import { fitTerminal } from "./ui.js";

export function emitPtyInput(tab, data) {
  if (!tab || !tab.socket || data == null) return; // NOSONAR
  // Convert \n to \r so that bash processes STT newlines and multiline pastes as command submissions
  const strData = String(data).replace(/\n/g, "\r"); // NOSONAR
  tab.socket.emit("pty-input", { input: strData });
}

export function sendToTerminal(data) {
  const tab = tabs.find((t) => t.id === activeTabId);
  let finalData = data;

  if (tab && tab.mobileProxy && tab.mobileProxy.modifierState) {
    // NOSONAR
    finalData = tab.mobileProxy.modifierState.applyModifiers(data);
  }

  if (tab && tab.socket && tab.state === "terminal") {
    // NOSONAR
    emitPtyInput(tab, finalData);
    tab.term.focus();
  }
}

export function adjustFontSize(delta) {
  const tab = tabs.find((t) => t.id === activeTabId);
  if (tab && tab.term) {
    // NOSONAR
    const newSize = Math.max(
      8,
      Math.min(40, tab.term.options.fontSize + delta),
    );
    tab.term.options.fontSize = newSize;
    globalState.currentFontSize = newSize;
    localStorage.setItem("gemini_font_size", globalState.currentFontSize);
    if (document.getElementById("theme-font")) {
      document.getElementById("theme-font").value = globalState.currentFontSize;
    }
    setTimeout(() => {
      fitTerminal(tab);
      if (tab.mobileProxy && tab.mobileProxy.ui) {
        // NOSONAR
        tab.mobileProxy.ui.alignWithCursor(tab.term);
      }
    }, 50);
  }
}
