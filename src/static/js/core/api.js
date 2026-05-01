// src/static/js/core/api.js
import { debugLog } from "./state.js";

let isRefreshingToken = false;
let tokenRefreshSubscribers = [];
let csrfRefreshAttempts = 0;
let lastCsrfRefreshTime = 0;

export const originalFetch = window.fetch;

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

export function initFetchOverride() {
  window.fetch = async function () {
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
      } catch (e) {
        // Ignore JSON parse errors for non-JSON responses
      }
    }
    return response;
  };
}
