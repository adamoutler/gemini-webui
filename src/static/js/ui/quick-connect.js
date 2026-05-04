import { debugLog, customFetch, escapeHtml } from "../core/api.js";
import { EventBus } from "../core/event-bus.js";
import { HostStateManager } from "./launcher.js";

export let currentQuickTabId = null;
export let currentQuickHost = null;
export function parseQuickInput(val) {
  if (!val) return null;
  // Format: user@host[:port] [directory]

  let user = "";
  let host = "";
  let port = "";
  let folder = "~";

  // 1. Split by space for directory
  const spaceIdx = val.indexOf(" ");
  if (spaceIdx !== -1) {
    folder = val.substring(spaceIdx + 1).trim() || "~";
    val = val.substring(0, spaceIdx).trim();
  }

  // 2. Split for user/host
  const userParts = val.split("@");
  if (userParts.length > 1) {
    user = userParts[0];
    val = userParts[1];
  } else {
    return null; // User is required
  }

  // 3. Split for host/port
  const hostParts = val.split(":");
  host = hostParts[0];
  if (hostParts.length > 1) {
    port = hostParts[1];
  }
  if (!host) return null;
  return {
    label: host,
    type: "ssh",
    target: port ? `${user}@${host}:${port}` : `${user}@${host}`,
    dir: folder,
  };
}
export async function saveHost(host) {
  await fetch("/api/hosts", {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify(host),
  });
}
export function quickConnectAction(tabId, action) {
  const input = document.getElementById(tabId + "_quick_input");
  const host = parseQuickInput(input.value);
  if (!host)
    return alert(
      "Invalid format. Use user@host, user@host:port, or user@host/folder",
    );
  currentQuickTabId = tabId;
  currentQuickHost = host;
  if (action === "key") {
    document.getElementById("quick-add-host-info").innerText =
      `Connecting to: ${host.target}`;
    document.getElementById("quick-add-key-modal").style.display = "block";
  } else {
    // Just connect
    saveHost(host).then(() => {
      startSession(tabId, host.type, host.target, host.dir, false);
    });
  }
}
export function closeQuickAddKey() {
  document.getElementById("quick-add-key-modal").style.display = "none";
}
export async function submitQuickAddKey() {
  const name = document.getElementById("quick-key-name").value;
  const text = document.getElementById("quick-key-text").value;
  if (!name || !text) return alert("Key name and text required");

  // 1. Save Key
  await fetch("/api/keys/text", {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify({
      name,
      key: text,
    }),
  });

  // 2. Save Host
  await saveHost(currentQuickHost);

  // 3. Close and Connect
  closeQuickAddKey();
  startSession(
    currentQuickTabId,
    currentQuickHost.type,
    currentQuickHost.target,
    currentQuickHost.dir,
    false,
  );
}
// --- End Quick Connect Logic ---

export function copyToClipboard(text) {
  if (navigator.clipboard && globalThis.isSecureContext) {
    navigator.clipboard
      .writeText(text)
      .then(() => alert("Copied to clipboard"));
  } else {
    // Fallback for non-secure contexts (dev environments)
    const textArea = document.createElement("textarea");
    textArea.value = text;
    textArea.style.position = "fixed";
    textArea.style.left = "-999999px";
    textArea.style.top = "-999999px";
    document.body.appendChild(textArea);
    textArea.focus();
    textArea.select();
    try {
      document.execCommand("copy");
      alert("Copied to clipboard (fallback mode)");
    } catch (err) {
      console.error("Fallback copy failed", err);
      alert("Copy failed. Please copy manually.");
    }
    document.body.removeChild(textArea);
  }
}
export function copyInstanceSnippet() {
  copyToClipboard(document.getElementById("instance-key-snippet").innerText);
}

document.addEventListener("DOMContentLoaded", async () => {
  try {
    await refreshCsrfToken();
  } catch (e) {
    console.error("Failed to initialize CSRF token:", e);
  }
  await loadPromptsFromServer();
});
// Prevent iOS/Android pull-to-refresh or page slide when swiping on controls
