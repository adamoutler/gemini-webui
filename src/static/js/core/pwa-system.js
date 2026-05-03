import { debugLog } from "./api.js";

let wakeLock = null;

import { globalState } from "./state.js";

export async function updateWakeLock() {
  const needsWakeLock = globalState.tabs.some(
    (t) => t.title && t.title.includes("Working"), // NOSONAR
  );
  if (needsWakeLock) {
    if (!wakeLock) {
      try {
        wakeLock = await navigator.wakeLock.request("screen");
        wakeLock.addEventListener("release", () => {
          wakeLock = null;
        });
      } catch (err) {
        console.error(`Wake Lock error: ${err.name}, ${err.message}`);
      }
    }
  } else {
    if (wakeLock) {
      // NOSONAR
      wakeLock.release().then(() => {
        wakeLock = null;
      });
    }
  }
}

document.addEventListener("visibilitychange", () => {
  if (document.visibilityState === "visible") {
    updateWakeLock();
  }
});

export function updatePageTitle() {
  updateWakeLock();
  const hasActionRequired = globalState.tabs.some(
    (t) => t.title && t.title.includes("✋"), // NOSONAR
  );
  const baseTitle = hasActionRequired
    ? "✋ Gemini WebUI"
    : globalState.originalPageTitle;
  if (!hasActionRequired) {
    // NOSONAR
    if (globalState.titleFlashInterval) {
      clearInterval(globalState.titleFlashInterval);
      globalState.titleFlashInterval = null;
    }
    document.title = baseTitle;
  } else {
    if (!document.hasFocus()) {
      // NOSONAR
      if (!globalState.titleFlashInterval) {
        document.title = baseTitle;
        const tempTitle = "⚠️ Action Required! ✋";
        globalState.titleFlashInterval = setInterval(() => {
          document.title = document.title === baseTitle ? tempTitle : baseTitle;
        }, 1000);
      }
    } else {
      if (globalState.titleFlashInterval) {
        clearInterval(globalState.titleFlashInterval);
        globalState.titleFlashInterval = null;
      }
      document.title = baseTitle;
    }
  }
}

globalThis.addEventListener("focus", () => {
  if (globalState.titleFlashInterval) {
    clearInterval(globalState.titleFlashInterval);
    globalState.titleFlashInterval = null;
    const hasActionRequired = globalState.tabs.some(
      (t) => t.title && t.title.includes("✋"), // NOSONAR
    );
    document.title = hasActionRequired
      ? "✋ Gemini WebUI"
      : globalState.originalPageTitle;
  }
});

export function checkInstallationStatus() {
  const isPWA =
    globalThis.matchMedia("(display-mode: standalone)").matches ||
    globalThis.navigator.standalone === true;
  const isIOS =
    /iPad|iPhone|iPod/.test(navigator.userAgent) && !globalThis.MSStream;
  const isSafari =
    /Safari/.test(navigator.userAgent) && !/Chrome/.test(navigator.userAgent);
  const isChrome =
    /CriOS/.test(navigator.userAgent) || /Chrome/.test(navigator.userAgent);
  const isFirefox =
    /FxiOS/.test(navigator.userAgent) || /Firefox/.test(navigator.userAgent);

  const isLocalhost =
    globalThis.location.hostname === "localhost" ||
    globalThis.location.hostname === "127.0.0.1";

  if (isLocalhost) {
    debugLog("Running on localhost, installation banner logic skipped");
    return;
  }

  const dismissed = localStorage.getItem("install_banner_dismissed");
  const installBanner = document.getElementById("install-banner");

  if (installBanner) {
    if (isPWA) {
      installBanner.style.display = "none";
    } else if (!dismissed && (isIOS || isChrome || isFirefox || isSafari)) {
      installBanner.style.display = "flex";

      const promptText = document.getElementById("install-prompt-text");
      if (isIOS && isSafari && promptText) {
        promptText.innerHTML =
          'Install Gemini WebUI: Tap <img src="/static/icon-192.png" style="width: 1em; height: 1em; vertical-align: middle; border-radius: 4px;" alt="share"> then "Add to Home Screen"';
      }
    }
  }
}

export function dismissInstallBanner() {
  const banner = document.getElementById("install-banner");
  if (banner) banner.style.display = "none";
  localStorage.setItem("install_banner_dismissed", "true");
}

export function initDesktopContextMenu() {
  if (
    /Android|webOS|iPhone|iPad|iPod|BlackBerry|IEMobile|Opera Mini/i.test(
      navigator.userAgent,
    )
  )
    return;
  document.addEventListener("contextmenu", (e) => {
    const isTextSelected = globalThis.getSelection().toString().length > 0;
    const isInput =
      e.target.tagName === "INPUT" ||
      e.target.tagName === "TEXTAREA" ||
      e.target.isContentEditable;
    if (isTextSelected || isInput) return;

    let el = e.target;
    let allowMenu = false;
    while (el) {
      if (el.classList && el.classList.contains("xterm-cursor-layer")) {
        // NOSONAR
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
    if (!allowMenu) e.preventDefault();
  });
}
