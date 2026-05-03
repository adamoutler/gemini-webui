export const globalState = {
  isMobile: false,
  tabs: [],
  customPrompts: [],
  currentEditPromptIndex: -1,
  activeTabId: null,
  ctrlActive: false,
  altActive: false,
  initialAutoResumeDone: false,
  launcherRefreshInterval: null,
  titleFlashInterval: null,
  originalPageTitle: "Gemini WebUI",
  currentFontSize: 14,
  mode: new URLSearchParams(globalThis.location.search).get("mode"),
  sessionId: new URLSearchParams(globalThis.location.search).get("session_id"),
  deepHost: new URLSearchParams(globalThis.location.search).get("host"),
  deepTarget: new URLSearchParams(globalThis.location.search).get("target"),
  deepDir: new URLSearchParams(globalThis.location.search).get("dir"),
};

export const DEFAULT_PROMPTS = [
  {
    name: "Explain Code",
    text: "Please explain the code in the current context.",
  },
  {
    name: "Refactor Code",
    text: "Suggest improvements and refactor the code in the current context.",
  },
  {
    name: "Summarize File",
    text: "Provide a high-level summary of the file's purpose and functionality.",
  },
  {
    name: "Gemini Audit",
    text: "Please run a security audit on the current context.",
  },
];

export async function loadPromptsFromServer() {
  try {
    const response = await fetch("/api/prompts");
    if (response.ok) {
      globalState.customPrompts = await response.json();
    }
  } catch (e) {
    console.error("Failed to load prompts from server:", e);
    try {
      globalState.customPrompts =
        JSON.parse(localStorage.getItem("custom_prompts")) || [];
    } catch (err) {
      // NOSONAR
      globalState.customPrompts = [];
    }
  }
}

export function getCustomPrompts() {
  return globalState.customPrompts;
}

if (typeof window !== "undefined") {
  // NOSONAR
  globalThis.globalState = globalState;
  globalThis.DEFAULT_PROMPTS = DEFAULT_PROMPTS;
  globalThis.loadPromptsFromServer = loadPromptsFromServer;
  globalThis.getCustomPrompts = getCustomPrompts;

  // For backwards compatibility before full ESM conversion
  Object.defineProperty(window, "tabs", {
    // NOSONAR
    get: () => globalState.tabs,
    set: (v) => {
      globalState.tabs = v;
    },
  });
  Object.defineProperty(window, "activeTabId", {
    // NOSONAR
    get: () => globalState.activeTabId,
    set: (v) => {
      globalState.activeTabId = v;
    },
  });
  Object.defineProperty(window, "customPrompts", {
    // NOSONAR
    get: () => globalState.customPrompts,
    set: (v) => {
      globalState.customPrompts = v;
    },
  });
  Object.defineProperty(window, "ctrlActive", {
    // NOSONAR
    get: () => globalState.ctrlActive,
    set: (v) => {
      globalState.ctrlActive = v;
    },
  });
  Object.defineProperty(window, "altActive", {
    // NOSONAR
    get: () => globalState.altActive,
    set: (v) => {
      globalState.altActive = v;
    },
  });
  Object.defineProperty(window, "currentEditPromptIndex", {
    // NOSONAR
    get: () => globalState.currentEditPromptIndex,
    set: (v) => {
      globalState.currentEditPromptIndex = v;
    },
  });
  Object.defineProperty(window, "initialAutoResumeDone", {
    // NOSONAR
    get: () => globalState.initialAutoResumeDone,
    set: (v) => {
      globalState.initialAutoResumeDone = v;
    },
  });
  Object.defineProperty(window, "launcherRefreshInterval", {
    // NOSONAR
    get: () => globalState.launcherRefreshInterval,
    set: (v) => {
      globalState.launcherRefreshInterval = v;
    },
  });
  Object.defineProperty(window, "titleFlashInterval", {
    // NOSONAR
    get: () => globalState.titleFlashInterval,
    set: (v) => {
      globalState.titleFlashInterval = v;
    },
  });
  Object.defineProperty(window, "originalPageTitle", {
    // NOSONAR
    get: () => globalState.originalPageTitle,
    set: (v) => {
      globalState.originalPageTitle = v;
    },
  });

  // URL params mappings
  Object.defineProperty(window, "mode", { get: () => globalState.mode }); // NOSONAR
  Object.defineProperty(window, "sessionId", {
    // NOSONAR
    get: () => globalState.sessionId,
  });
  Object.defineProperty(window, "deepHost", {
    // NOSONAR
    get: () => globalState.deepHost,
  });
  Object.defineProperty(window, "deepTarget", {
    // NOSONAR
    get: () => globalState.deepTarget,
  });
  Object.defineProperty(window, "deepDir", { get: () => globalState.deepDir }); // NOSONAR
}
