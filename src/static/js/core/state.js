export let globalState = {
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

export let DEFAULT_PROMPTS = [
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
      globalState.customPrompts = [];
    }
  }
}

export function getCustomPrompts() {
  return globalState.customPrompts;
}

if (typeof globalThis.window !== "undefined") {
  globalThis.globalState = globalState;
  globalThis.DEFAULT_PROMPTS = DEFAULT_PROMPTS;
  globalThis.loadPromptsFromServer = loadPromptsFromServer;
  globalThis.getCustomPrompts = getCustomPrompts;

  // For backwards compatibility before full ESM conversion
  Object.defineProperty(globalThis.window, "tabs", {
    get: () => globalState.tabs,
    set: (v) => {
      globalState.tabs = v;
    },
  });
  Object.defineProperty(globalThis.window, "activeTabId", {
    get: () => globalState.activeTabId,
    set: (v) => {
      globalState.activeTabId = v;
    },
  });
  Object.defineProperty(globalThis.window, "customPrompts", {
    get: () => globalState.customPrompts,
    set: (v) => {
      globalState.customPrompts = v;
    },
  });
  Object.defineProperty(globalThis.window, "ctrlActive", {
    get: () => globalState.ctrlActive,
    set: (v) => {
      globalState.ctrlActive = v;
    },
  });
  Object.defineProperty(globalThis.window, "altActive", {
    get: () => globalState.altActive,
    set: (v) => {
      globalState.altActive = v;
    },
  });
  Object.defineProperty(globalThis.window, "currentEditPromptIndex", {
    get: () => globalState.currentEditPromptIndex,
    set: (v) => {
      globalState.currentEditPromptIndex = v;
    },
  });
  Object.defineProperty(globalThis.window, "initialAutoResumeDone", {
    get: () => globalState.initialAutoResumeDone,
    set: (v) => {
      globalState.initialAutoResumeDone = v;
    },
  });
  Object.defineProperty(globalThis.window, "launcherRefreshInterval", {
    get: () => globalState.launcherRefreshInterval,
    set: (v) => {
      globalState.launcherRefreshInterval = v;
    },
  });
  Object.defineProperty(globalThis.window, "titleFlashInterval", {
    get: () => globalState.titleFlashInterval,
    set: (v) => {
      globalState.titleFlashInterval = v;
    },
  });
  Object.defineProperty(globalThis.window, "originalPageTitle", {
    get: () => globalState.originalPageTitle,
    set: (v) => {
      globalState.originalPageTitle = v;
    },
  });

  // URL params mappings
  Object.defineProperty(globalThis.window, "mode", { get: () => globalState.mode });
  Object.defineProperty(globalThis.window, "sessionId", {
    get: () => globalState.sessionId,
  });
  Object.defineProperty(globalThis.window, "deepHost", {
    get: () => globalState.deepHost,
  });
  Object.defineProperty(globalThis.window, "deepTarget", {
    get: () => globalState.deepTarget,
  });
  Object.defineProperty(globalThis.window, "deepDir", { get: () => globalState.deepDir });
}
