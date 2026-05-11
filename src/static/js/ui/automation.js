export function openAutomationDashboard() {
  document.getElementById("automation-modal").style.display = "block";
  loadAutomationHosts();
  refreshSchedules();
  refreshHistory();
}

export function closeAutomationDashboard() {
  document.getElementById("automation-modal").style.display = "none";
}

export function switchAutomationTab(tabName) {
  if (tabName === "schedules") {
    document.getElementById("automation-schedules-view").style.display =
      "block";
    document.getElementById("automation-history-view").style.display = "none";
    document.getElementById("tab-schedules").style.background = "#007bff";
    document.getElementById("tab-schedules").style.color = "white";
    document.getElementById("tab-schedules").style.border = "none";
    document.getElementById("tab-history").style.background = "transparent";
    document.getElementById("tab-history").style.color = "inherit";
    document.getElementById("tab-history").style.border = "1px solid #ccc";
  } else {
    document.getElementById("automation-schedules-view").style.display = "none";
    document.getElementById("automation-history-view").style.display = "block";
    document.getElementById("tab-history").style.background = "#007bff";
    document.getElementById("tab-history").style.color = "white";
    document.getElementById("tab-history").style.border = "none";
    document.getElementById("tab-schedules").style.background = "transparent";
    document.getElementById("tab-schedules").style.color = "inherit";
    document.getElementById("tab-schedules").style.border = "1px solid #ccc";
  }
}

export async function loadAutomationHosts() {
  const hostSelect = document.getElementById("automation-host-select");
  if (!hostSelect) return;

  hostSelect.innerHTML = '<option value="">Local Machine (Default)</option>';
  try {
    const res = await fetch("/api/hosts");
    const hosts = await res.json();
    hosts.forEach((host) => {
      const option = document.createElement("option");
      option.value = `${host.target}:${host.dir || "~"}`;
      option.textContent = `${host.label} (${host.target})`;
      hostSelect.appendChild(option);
    });
  } catch (err) {
    console.error("Error loading hosts for automation:", err);
  }
}

export async function saveAutomationSchedule() {
  const nameValue = document.getElementById("automation-name")?.value || "";
  const hostValue = document.getElementById("automation-host-select").value;
  const prompt = document.getElementById("automation-prompt").value;
  const startTime = document.getElementById("automation-start-time").value;
  const freq = document.getElementById("automation-recurrence-freq").value;
  const unit = document.getElementById("automation-recurrence-unit").value;
  const waitIdle = document.getElementById("automation-wait-idle").checked;

  if (!prompt.trim()) {
    alert("Please enter a command or prompt.");
    return;
  }

  // To be integrated with the backend v1 API when ready
  const scheduleData = {
    name: nameValue,
    target: hostValue || "local",
    prompt,
    startTime,
    recurrence: unit === "once" ? null : `${freq} ${unit}`,
    mode: waitIdle ? "heuristic" : "strict",
  };

  try {
    const csrfToken = document
      .querySelector('meta[name="csrf-token"]')
      ?.getAttribute("content");
    const res = await fetch("/api/v1/schedules", {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "X-CSRFToken": csrfToken || "",
      },
      body: JSON.stringify(scheduleData),
    });
    if (!res.ok) {
      const err = await res.json();
      throw new Error(err.error || "Failed to save schedule");
    }
    console.log("Schedule saved successfully");
    document.getElementById("automation-prompt").value = "";
    refreshSchedules();
  } catch (err) {
    console.error("Error saving schedule:", err);
    alert("Error: " + err.message);
  }
}

export async function refreshSchedules() {
  const list = document.getElementById("automation-schedules-list");
  if (!list) return;

  list.innerHTML = "<p>Loading schedules...</p>";
  try {
    const res = await fetch("/api/v1/schedules");
    if (!res.ok) throw new Error("Failed to fetch schedules");
    const schedules = await res.json();

    if (schedules.length === 0) {
      list.innerHTML = "<p>No active schedules retrieved yet.</p>";
      return;
    }

    list.innerHTML = "";
    schedules.forEach((sched) => {
      const item = document.createElement("div");
      item.style.borderBottom = "1px solid #eee";
      item.style.padding = "5px";
      item.style.marginBottom = "5px";
      item.style.display = "flex";
      item.style.flexDirection = "column";
      item.style.gap = "5px";

      const name = sched.name || "Unnamed Task";
      const target = sched.target_host_id || "local";
      const promptSnippet =
        sched.task_prompt.length > 50
          ? sched.task_prompt.substring(0, 50) + "..."
          : sched.task_prompt;

      const nextRun = sched.next_run_at
        ? new Date(sched.next_run_at * 1000).toLocaleString()
        : "Manual/Pending";
      let isActive = sched.is_active ? "Active" : "Inactive";
      if (
        sched.is_active &&
        sched.next_run_at &&
        Date.now() / 1000 >= sched.next_run_at
      ) {
        isActive = "Queued (Waiting for Idle)";
      }
      const mode = sched.wait_for_idle ? "Wait for Idle" : "Strict";

      item.innerHTML = `
        <div style="display: flex; justify-content: space-between; align-items: center;">
          <strong>${name}</strong>
          <span style="font-size: 0.85em; color: ${
            sched.is_active ? "green" : "orange"
          };">${isActive}</span>
        </div>
        <div style="font-size: 0.9em;">
          <div>Host: ${target} (${mode})</div>
          <div>Prompt: <code style="background: #f4f4f4; padding: 2px;">${promptSnippet}</code></div>
          <div>Next Run: ${nextRun}</div>
          <div>Cron: ${sched.cron_expr}</div>
        </div>
        <div style="display: flex; gap: 5px; margin-top: 5px;">
          <button data-onclick="executeAutomationSchedule('${
            sched.id
          }')" style="padding: 3px 8px; background: #007bff; color: white; border: none; border-radius: 3px; cursor: pointer; font-size: 0.85em;">Execute Now</button>
          <button data-onclick="deleteAutomationSchedule('${
            sched.id
          }')" style="padding: 3px 8px; background: #dc3545; color: white; border: none; border-radius: 3px; cursor: pointer; font-size: 0.85em;">Delete</button>
        </div>
      `;
      list.appendChild(item);
    });
  } catch (err) {
    console.error("Error refreshing schedules:", err);
    list.innerHTML = `<p style="color: red;">Error: ${err.message}</p>`;
  }
}

export async function deleteAutomationSchedule(id) {
  if (!confirm("Are you sure you want to delete this schedule?")) return;

  try {
    const csrfToken = document
      .querySelector('meta[name="csrf-token"]')
      ?.getAttribute("content");
    const res = await fetch(`/api/v1/schedules/${id}`, {
      method: "DELETE",
      headers: {
        "X-CSRFToken": csrfToken || "",
      },
    });
    if (!res.ok) throw new Error("Failed to delete schedule");
    refreshSchedules();
  } catch (err) {
    console.error("Error deleting schedule:", err);
    alert("Error: " + err.message);
  }
}

export async function executeAutomationSchedule(id) {
  try {
    const csrfToken = document
      .querySelector('meta[name="csrf-token"]')
      ?.getAttribute("content");
    const res = await fetch(`/api/v1/schedules/${id}/execute`, {
      method: "POST",
      headers: {
        "X-CSRFToken": csrfToken || "",
      },
    });
    if (!res.ok) {
      const err = await res.json();
      throw new Error(err.error || "Failed to execute schedule");
    }
    alert("Task executed. It will run in a new terminal window.");
  } catch (err) {
    console.error("Error executing schedule:", err);
    alert("Error: " + err.message);
  }
}

export async function refreshHistory() {
  const list = document.getElementById("automation-history-list");
  const logViewer = document.getElementById("automation-log-viewer");
  if (!list) return;

  list.innerHTML = "<p>Loading history...</p>";
  if (logViewer) logViewer.style.display = "none";

  try {
    const res = await fetch("/api/v1/schedules/history");
    if (!res.ok) throw new Error("Failed to fetch history");
    const jobs = await res.json();

    if (jobs.length === 0) {
      list.innerHTML = "<p>No history available.</p>";
      return;
    }

    list.innerHTML = "";
    jobs.forEach((job) => {
      const item = document.createElement("div");
      item.style.borderBottom = "1px solid #eee";
      item.style.padding = "5px";
      item.style.marginBottom = "5px";

      const timeStr = new Date(job.timestamp * 1000).toLocaleString();
      const statusColor =
        job.status === "error"
          ? "red"
          : job.status === "completed"
            ? "green"
            : "orange";

      item.innerHTML = `
        <div style="display: flex; justify-content: space-between;">
          <span style="font-size: 0.9em;"><strong>${timeStr}</strong> - <span style="color: ${statusColor};">${
            job.status
          }</span></span>
          <button style="padding: 2px 5px; font-size: 0.8em;" onclick="document.getElementById('automation-log-viewer').innerText = decodeURIComponent('${encodeURIComponent(
            job.output || "No output",
          )}'); document.getElementById('automation-log-viewer').style.display='block';">View Log</button>
        </div>
        <div style="font-size: 0.85em; color: #555;">Exit Code: ${
          job.exit_code !== null ? job.exit_code : "N/A"
        }</div>
      `;
      list.appendChild(item);
    });
  } catch (err) {
    console.error("Error refreshing history:", err);
    list.innerHTML = `<p style="color: red;">Error: ${err.message}</p>`;
  }
}
