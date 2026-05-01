import {
  initThemeUI,
  copyToClipboard,
  envVarManager,
  renderLauncher,
  fetchWithCSRF,
} from "../../app.js";

let editingHostLabel = null;

export async function openSettings() {
  document.getElementById("settings-modal").style.display = "block";
  loadHosts();
  loadKeys();
  loadPublicKey();
  initThemeUI();
  loadSharedSessions();
}
export async function loadSharedSessions() {
  const list = document.getElementById("shared-sessions-list");
  if (!list) return;
  list.innerHTML =
    '<div class="js-style-a06f1d">Loading session snapshots...</div>';
  try {
    const response = await fetch("/api/shares");
    if (response.ok) {
      const data = await response.json();
      const shares = data.shares || data; // handle if it's wrapped or array directly

      list.innerHTML = "";
      if (!shares || shares.length === 0) {
        list.innerHTML =
          '<div class="js-style-a674a2">No session snapshots.</div>';
        return;
      }

      // Note: API might return an object with keys or array, handle accordingly
      const shareArray = Array.isArray(shares)
        ? shares
        : Object.keys(shares).map((k) => ({
            id: k,
            ...shares[k],
          }));
      shareArray.forEach((share) => {
        const item = document.createElement("div");
        item.className = "session-item";
        item.style.display = "flex";
        item.style.justifyContent = "space-between";
        item.style.alignItems = "center";
        item.style.borderBottom = "1px solid #444";
        item.style.padding = "10px";
        const dateStr = share.created_at
          ? new Date(share.created_at * 1000).toLocaleString()
          : "Unknown";
        const shareId = share.id || share.uuid; // handle both just in case
        const linkUrl = window.location.origin + "/s/" + shareId;
        const sessionName = share.session_name || "Session Snapshot";
        item.innerHTML = `
                            <div class="js-style-b2fad5">
                                <div class="js-style-68bda4">${sessionName}</div>
                                <div class="js-style-339053">Created: ${dateStr}</div>
                            </div>
                            <div class="js-style-611fa3">
                                <button class="primary small" data-onclick="viewSharedSession('${shareId}')">View</button>
                                <button class="success small" data-onclick="copyToClipboard('${linkUrl}')">Copy</button>
                                <button class="danger small" data-onclick="deleteSharedSession('${shareId}')">Delete</button>
                            </div>
                        `;
        list.appendChild(item);
      });
    } else {
      list.innerHTML =
        '<div class="js-style-808abb">Failed to load session snapshots.</div>';
    }
  } catch (e) {
    console.error("Failed to load session snapshots", e);
    list.innerHTML =
      '<div class="js-style-808abb">Error loading session snapshots.</div>';
  }
}
export async function deleteSharedSession(uuid) {
  if (!confirm("Are you sure you want to delete this session snapshot?"))
    return;
  try {
    const response = await fetch("/api/shares/" + uuid, {
      method: "DELETE",
      headers: {
        "X-CSRFToken":
          document
            .querySelector('meta[name="csrf-token"]')
            ?.getAttribute("content") || "",
      },
    });
    if (response.ok) {
      loadSharedSessions();
    } else {
      const data = await response.json();
      alert("Failed to delete: " + (data.error || "Unknown error"));
    }
  } catch (e) {
    console.error("Failed to delete session snapshot", e);
    alert("Error deleting session snapshot.");
  }
}
export function viewSharedSession(uuid) {
  const previewModal = document.getElementById("preview-modal");
  const iframe = document.getElementById("preview-iframe");
  if (previewModal && iframe) {
    iframe.src = "/s/" + uuid;
    previewModal.style.display = "block";
  }
}
export function closePreviewModal() {
  const previewModal = document.getElementById("preview-modal");
  const iframe = document.getElementById("preview-iframe");
  if (previewModal) {
    previewModal.style.display = "none";
  }
  if (iframe) {
    iframe.src = ""; // Clear iframe to stop loading
  }
}
export async function loadPublicKey() {
  try {
    const response = await fetch("/api/keys/public");
    if (response.ok) {
      const data = await response.json();
      document.getElementById("public-key-text").innerText = data.key;
      document.getElementById("instance-key-snippet").innerText =
        `mkdir -p ~/.ssh && echo "${data.key}" >> ~/.ssh/authorized_keys && chmod 700 ~/.ssh && chmod 600 ~/.ssh/authorized_keys`;
      document.getElementById("public-key-container").style.display = "block";
    }
  } catch (e) {
    console.error("Could not load public key", e);
  }
}
export function copyPublicKey() {
  copyToClipboard(document.getElementById("public-key-text").innerText);
}
export async function rotateInstanceKey() {
  if (
    !confirm(
      "Are you sure you want to rotate the instance key? All remote hosts using the current key will lose access until updated with the new one.",
    )
  )
    return;
  try {
    const response = await fetch("/api/keys/rotate", {
      method: "POST",
    });
    if (response.ok) {
      const data = await response.json();
      alert("Instance key rotated successfully.");
      loadPublicKey(); // Refresh UI
    } else {
      const err = await response.json();
      alert("Error rotating key: " + err.message);
    }
  } catch (e) {
    console.error("Rotate failed", e);
  }
}
export async function loadHosts() {
  const hosts = await (await fetch("/api/hosts")).json();
  const list = document.getElementById("hosts-list");
  list.innerHTML = "";
  hosts.forEach((host) => {
    const item = document.createElement("div");
    item.className = "session-item";
    item.style.cursor = "pointer";
    item.onclick = () => populateHostForm(host);
    item.innerHTML =
      `<div class="session-info"><span class="js-style-7160a4">${
        host.label
      }</span><span class="js-style-c27a65">${host.target || "local"} ${
        host.dir || ""
      }</span></div>` +
      (host.label !== "local"
        ? `<button class="danger small" data-onclick="event.stopPropagation(); removeHost('${host.label}')">Delete</button>`
        : "");
    list.appendChild(item);
  });
}
export function populateHostForm(host) {
  document.getElementById("new-host-label").value = host.label;
  document.getElementById("new-host-target").value = host.target || "";
  document.getElementById("new-host-dir").value = host.dir || "";
  if (envVarManager) envVarManager.load(host.env_vars || {});
  if (host.label === "local") {
    editingHostLabel = null;
    setHostMode("add"); // Cannot edit default local, force add mode
  } else {
    editingHostLabel = host.label;
    setHostMode("edit");
  }
}
export function setHostMode(mode) {
  const addBtn = document.getElementById("add-mode-btn");
  const editBtn = document.getElementById("edit-mode-btn");
  const submitBtn = document.getElementById("add-host-btn");
  const labelInput = document.getElementById("new-host-label");
  if (mode === "edit") {
    if (labelInput.value === "local") {
      alert(
        "The default 'local' host cannot be edited. It will be used as a template for a new host.",
      );
      setHostMode("add");
      return;
    }
    addBtn.style.opacity = "0.5";
    addBtn.style.fontWeight = "normal";
    editBtn.style.opacity = "1";
    editBtn.style.fontWeight = "bold";
    submitBtn.innerText = "Update Host";
    submitBtn.className = "primary";
  } else {
    editingHostLabel = null;
    addBtn.style.opacity = "1";
    addBtn.style.fontWeight = "bold";
    editBtn.style.opacity = "0.5";
    editBtn.style.fontWeight = "normal";
    submitBtn.innerText = "Add Host";
    submitBtn.className = "success";
  }
}
export function clearHostForm() {
  document.getElementById("new-host-label").value = "";
  document.getElementById("new-host-target").value = "";
  document.getElementById("new-host-dir").value = "";
  if (envVarManager) envVarManager.clear();
  editingHostLabel = null;
  setHostMode("add");
}
export async function submitHostForm() {
  const label = document.getElementById("new-host-label").value;
  const target = document.getElementById("new-host-target").value;
  const dir = document.getElementById("new-host-dir").value;
  const submitBtn = document.getElementById("add-host-btn");
  if (!label) return alert("Label required");
  if (label === "local" && submitBtn.innerText === "Update Host") {
    return alert("Cannot update protected 'local' host.");
  }
  const host = {
    label,
    type: target ? "ssh" : "local",
    target,
    dir,
    env_vars: envVarManager ? envVarManager.get() : {},
    old_label: editingHostLabel, // Pass to server for in-place update
  };
  const response = await fetch("/api/hosts", {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify(host),
  });
  if (response.ok) {
    const originalText = submitBtn.innerText;
    submitBtn.innerText = originalText + " ✓";
    setTimeout(() => {
      submitBtn.innerText = originalText;
    }, 2000);
    editingHostLabel = label; // Update current tracking
    loadHosts();
  } else {
    alert("Failed to save host.");
  }
}
export async function removeHost(label) {
  if (!confirm(`Remove host ${label}?`)) return;
  await fetch(`/api/hosts/${encodeURIComponent(label)}`, {
    method: "DELETE",
  });
  loadHosts();
}
export async function loadKeys() {
  const keys = await (await fetch("/api/keys")).json();
  const list = document.getElementById("key-list");
  list.innerHTML = "";
  if (keys.length === 0)
    list.innerHTML = '<li class="js-style-52b0fe">No keys found.</li>';
  keys.forEach((key) => {
    const li = document.createElement("li");
    li.className = "session-item";
    li.innerHTML = `<div class="session-info">${key}</div><button class="danger small" data-onclick="removeKey('${key}')">Delete</button>`;
    list.appendChild(li);
  });
}
export async function removeKey(filename) {
  if (!confirm(`Delete key ${filename}?`)) return;
  await fetch(`/api/keys/${filename}`, {
    method: "DELETE",
  });
  loadKeys();
}
export function closeSettings() {
  document.getElementById("settings-modal").style.display = "none";
  tabs.forEach((t) => {
    if (t.state === "launcher") renderLauncher(t.id);
  });
}
export function exportSettings() {
  window.location.href = "/api/settings/export";
}
export function importSettings(event) {
  const file = event.target.files[0];
  if (!file) return;
  if (
    !confirm(
      "Warning: Importing settings will overwrite your current configuration. Are you sure you want to proceed?",
    )
  ) {
    event.target.value = "";
    return;
  }
  const formData = new FormData();
  formData.append("file", file);
  fetch("/api/settings/import", {
    method: "POST",
    body: formData,
  })
    .then((response) => response.json())
    .then((data) => {
      if (data.success) {
        alert(
          "Settings imported successfully. The application will now reload.",
        );
        window.location.reload();
      } else {
        alert("Failed to import settings: " + (data.error || "Unknown error"));
      }
    })
    .catch((err) => {
      console.error(err);
      alert("An error occurred during import.");
    })
    .finally(() => {
      event.target.value = "";
    });
}
export async function savePastedKey() {
  const name = document.getElementById("ssh-key-name").value;
  const text = document.getElementById("ssh-key-text").value;
  if (!name || !text) return alert("Name and key text required");
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
  document.getElementById("ssh-key-name").value = "";
  document.getElementById("ssh-key-text").value = "";
  loadKeys();
}
export async function uploadKeyFile() {
  const fileInput = document.getElementById("ssh-key-file");
  if (!fileInput.files.length) return alert("Please select a file to upload");
  const file = fileInput.files[0];
  const formData = new FormData();
  formData.append("file", file);
  try {
    const response = await fetchWithCSRF("/api/keys/upload", {
      method: "POST",
      headers: {
        "X-CSRFToken":
          document
            .querySelector('meta[name="csrf-token"]')
            ?.getAttribute("content") || "",
      },
      body: formData,
    });
    if (response.ok) {
      fileInput.value = "";
      loadKeys();
    } else {
      let errorMessage = "Unknown error";
      const contentType = response.headers.get("content-type");
      if (contentType && contentType.indexOf("application/json") !== -1) {
        try {
          const data = await response.json();
          errorMessage = data.error || data.message || errorMessage;
        } catch (e) {
          errorMessage = "Failed to parse error response.";
        }
      } else {
        errorMessage = await response.text();
      }
      if (response.status === 400 || response.status === 403) {
        errorMessage += " (Auth/CSRF error - please reload the page)";
      }
      alert("Upload failed: " + errorMessage);
    }
  } catch (err) {
    alert("Upload failed: " + err.message);
  }
}

// Prevent iOS/Android pull-to-refresh or page slide when swiping on controls

window.openSettings = openSettings;
window.closeSettings = closeSettings;
window.loadSharedSessions = loadSharedSessions;
window.deleteSharedSession = deleteSharedSession;
window.viewSharedSession = viewSharedSession;
window.closePreviewModal = closePreviewModal;
window.loadPublicKey = loadPublicKey;
window.copyPublicKey = copyPublicKey;
window.rotateInstanceKey = rotateInstanceKey;
window.loadHosts = loadHosts;
window.populateHostForm = populateHostForm;
window.setHostMode = setHostMode;
window.clearHostForm = clearHostForm;
window.submitHostForm = submitHostForm;
window.removeHost = removeHost;
window.loadKeys = loadKeys;
window.removeKey = removeKey;
window.exportSettings = exportSettings;
window.importSettings = importSettings;
window.savePastedKey = savePastedKey;
window.uploadKeyFile = uploadKeyFile;
