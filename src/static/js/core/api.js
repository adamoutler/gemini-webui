export function escapeHtml(str) {
  if (!str) return "";
  return String(str)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#039;");
}

export function filterTerminalFluff(text) {
  if (!text) return "";
  let lines = text.split("\n");
  lines = lines.map((line) => {
    if (line.includes("workspace (") && line.includes("branch:"))
      return " ".repeat(line.length);
    if (line.includes("Shift+Tab to accept edits"))
      return " ".repeat(line.length);
    if (/^[\u2500-\u259F \t\r]+$/.test(line) && /[\u2500-\u259F]/.test(line)) {
      return " ".repeat(line.length);
    }
    let cleaned = line.replace(/[\u2500-\u259F]/g, " ");
    return cleaned;
  });
  return lines.join("\n");
}

let ENABLE_DEBUG = false;
try {
  ENABLE_DEBUG = localStorage.getItem("GEMINI_DEBUG") === "true";
} catch (e) {}

export function setDebug(enabled) {
  ENABLE_DEBUG = !!enabled;
  if (enabled) {
    localStorage.setItem("GEMINI_DEBUG", "true");
    console.log("Verbose debugging enabled. To disable, run: setDebug(false)");
  } else {
    localStorage.removeItem("GEMINI_DEBUG");
    console.log("Verbose debugging disabled. To enable, run: setDebug(true)");
  }
  if (typeof window !== "undefined") globalThis.ENABLE_DEBUG = ENABLE_DEBUG;
}

export function debugLog(...args) {
  if (ENABLE_DEBUG) {
    console.log(...args);
  }
}

let isRefreshingToken = false;
let tokenRefreshSubscribers = [];
let csrfRefreshAttempts = 0;
let lastCsrfRefreshTime = 0;

export async function refreshCsrfToken() {
  const now = Date.now();
  if (now - lastCsrfRefreshTime < 500) {
    csrfRefreshAttempts++;
  } else {
    csrfRefreshAttempts = 0;
  }
  lastCsrfRefreshTime = now;

  if (csrfRefreshAttempts > 10) {
    const details = document.getElementById("connection-issue-details");
    if (details) details.innerText = "Error: Too many CSRF refresh attempts.";
    const modal = document.getElementById("connection-issue-modal");
    if (modal) modal.style.display = "block";
    throw new Error("Too many CSRF refresh attempts");
  }

  if (isRefreshingToken) {
    return new Promise((resolve) => tokenRefreshSubscribers.push(resolve));
  }
  isRefreshingToken = true;
  try {
    const response = await originalFetch("/api/csrf-token", {
      cache: "no-store",
      credentials: "same-origin",
    });
    if (!response.ok) throw new Error("Failed to fetch token");
    const data = await response.json();
    const newToken = data.csrf_token;
    const metaTag = document.querySelector('meta[name="csrf-token"]');
    if (metaTag) metaTag.setAttribute("content", newToken);
    tokenRefreshSubscribers.forEach((cb) => cb(newToken));
    return newToken;
  } finally {
    isRefreshingToken = false;
    tokenRefreshSubscribers = [];
  }
}

export const originalFetch =
  typeof window !== "undefined" ? globalThis.fetch : fetch;

export async function customFetch() {
  let currentCsrfToken = document
    .querySelector('meta[name="csrf-token"]')
    ?.getAttribute("content");
  let [resource, config] = arguments;
  if (config === undefined) {
    config = {};
  }

  const injectToken = (token, cfg) => {
    if (
      cfg.method &&
      ["POST", "PUT", "DELETE", "PATCH"].includes(cfg.method.toUpperCase())
    ) {
      if (cfg.headers instanceof Headers) {
        if (token) cfg.headers.set("X-CSRFToken", token);
      } else {
        cfg.headers = cfg.headers || {};
        if (token) cfg.headers["X-CSRFToken"] = token;
      }
    }
  };

  injectToken(currentCsrfToken, config);

  let response = await originalFetch(resource, config);

  if (response.status === 400 || response.status === 403) {
    try {
      const clonedResponse = response.clone();
      const data = await clonedResponse.json();
      if (data && data.csrf_expired === true && !config.skipCsrfReload) {
        const newToken = await refreshCsrfToken();
        injectToken(newToken, config);
        response = await originalFetch(resource, config);
      }
    } catch (e) {}
  }
  return response;
}

if (typeof window !== "undefined") {
  globalThis.fetch = customFetch;
  globalThis.originalFetch = originalFetch;
  globalThis.escapeHtml = escapeHtml;
  globalThis.filterTerminalFluff = filterTerminalFluff;
  globalThis.setDebug = setDebug;
  globalThis.debugLog = debugLog;
  globalThis.ENABLE_DEBUG = ENABLE_DEBUG;
  globalThis.refreshCsrfToken = refreshCsrfToken;
}

export async function fetchWithCSRF(url, options = {}) {
  options.headers = options.headers || {};
  options.headers["X-CSRFToken"] =
    document
      .querySelector('meta[name="csrf-token"]')
      ?.getAttribute("content") || "";
  options.skipCsrfReload = true; // Prevent global fetch from reloading page on 400/403

  let response = await fetch(url, options);
  if (response.status === 400 || response.status === 403) {
    try {
      const newToken = await refreshCsrfToken();
      options.headers["X-CSRFToken"] = newToken;
      response = await fetch(url, options);
    } catch (e) {
      console.error("Failed to refresh CSRF token on retry:", e);
    }
  }
  return response;
}
