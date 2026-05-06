import { globalState } from "../core/state.js";
import { fitTerminal } from "../terminal/ui.js";

const getIsMobile = () =>
  document.documentElement.classList.contains("is-mobile");
const getDefaultFontSize = () => (getIsMobile() ? 10 : 14);

export let terminalTheme = {
  background: "#1e1e1e",
  foreground: "#d4d4d4",
  cursor: "#ffffff",
  selection: "#264f78",
  black: "#000000",
  red: "#cd3131",
  green: "#0dbc79",
  yellow: "#e5e510",
  blue: "#2472c8",
  magenta: "#bc3fbc",
  cyan: "#11a8cd",
  white: "#e5e5e5",
  brightBlack: "#666666",
  brightRed: "#f14c4c",
  brightGreen: "#23d18b",
  brightYellow: "#f5f543",
  brightBlue: "#3b8eea",
  brightMagenta: "#d670d6",
  brightCyan: "#29b8db",
  brightWhite: "#e5e5e5",
};

export function initializeTheme() {
  let savedTheme = localStorage.getItem("gemini_theme");
  let customTheme = savedTheme ? JSON.parse(savedTheme) : {};
  let customFontSize = localStorage.getItem("gemini_font_size");
  globalState.currentFontSize = customFontSize
    ? Number.parseInt(customFontSize)
    : getDefaultFontSize();

  Object.assign(terminalTheme, {
    background: customTheme.background || "#1e1e1e",
    foreground: customTheme.foreground || "#d4d4d4",
    cursor: customTheme.cursor || "#ffffff",
  });

  if (typeof globalThis.window !== "undefined") globalThis.terminalTheme = terminalTheme;

  // Initialize CSS variables immediately to reflect any saved theme
  document.documentElement.style.setProperty(
    "--terminal-bg",
    terminalTheme.background,
  );
  document.documentElement.style.setProperty(
    "--terminal-fg",
    terminalTheme.foreground,
  );
}

export function initThemeUI() {
  document.documentElement.style.setProperty(
    "--terminal-bg",
    terminalTheme.background,
  );
  document.documentElement.style.setProperty(
    "--terminal-fg",
    terminalTheme.foreground,
  );

  const bgEl = document.getElementById("theme-bg");
  const fgEl = document.getElementById("theme-fg");
  const cursorEl = document.getElementById("theme-cursor");
  const fontEl = document.getElementById("theme-font");

  if (bgEl) bgEl.value = terminalTheme.background;
  if (fgEl) fgEl.value = terminalTheme.foreground;
  if (cursorEl) cursorEl.value = terminalTheme.cursor;
  if (fontEl) fontEl.value = globalState.currentFontSize;
}

export function applyTheme() {
  terminalTheme.background = document.getElementById("theme-bg").value;
  terminalTheme.foreground = document.getElementById("theme-fg").value;
  terminalTheme.cursor = document.getElementById("theme-cursor").value;
  globalState.currentFontSize =
    Number.parseInt(document.getElementById("theme-font").value) ||
    getDefaultFontSize();
  localStorage.setItem(
    "gemini_theme",
    JSON.stringify({
      background: terminalTheme.background,
      foreground: terminalTheme.foreground,
      cursor: terminalTheme.cursor,
    }),
  );
  localStorage.setItem("gemini_font_size", globalState.currentFontSize);

  // Set CSS variables for global styling matching the theme
  document.documentElement.style.setProperty(
    "--terminal-bg",
    terminalTheme.background,
  );
  document.documentElement.style.setProperty(
    "--terminal-fg",
    terminalTheme.foreground,
  );

  // Apply to all open terminals
  globalState.tabs.forEach((tab) => {
    if (tab.term) {
      tab.term.options.theme = terminalTheme;
      tab.term.options.fontSize = globalState.currentFontSize;
      fitTerminal(tab);
    }
  });
}

export function resetTheme() {
  localStorage.removeItem("gemini_theme");
  localStorage.removeItem("gemini_font_size");
  terminalTheme.background = "#1e1e1e";
  terminalTheme.foreground = "#d4d4d4";
  terminalTheme.cursor = "#ffffff";
  globalState.currentFontSize = getDefaultFontSize();
  initThemeUI();

  // Apply immediately to terminals
  globalState.tabs.forEach((tab) => {
    if (tab.term) {
      tab.term.options.theme = terminalTheme;
      tab.term.options.fontSize = globalState.currentFontSize;
      fitTerminal(tab);
    }
  });
}

if (typeof globalThis.window !== "undefined") {
  globalThis.initThemeUI = initThemeUI;
  globalThis.applyTheme = applyTheme;
  globalThis.resetTheme = resetTheme;
}
