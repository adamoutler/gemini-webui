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
    target: hostValue || "local",
    prompt,
    startTime,
    recurrence: unit === "once" ? null : `${freq} ${unit}`,
    mode: waitIdle ? "heuristic" : "strict",
  };

  console.log("Saving schedule:", scheduleData);
  alert("Schedule saved (Mocked). Backend integration pending.");

  document.getElementById("automation-prompt").value = "";
  refreshSchedules();
}

export function refreshSchedules() {
  const list = document.getElementById("automation-schedules-list");
  if (list) {
    list.innerHTML = "<p>No active schedules retrieved yet.</p>";
  }
}

export function refreshHistory() {
  const list = document.getElementById("automation-history-list");
  if (list) {
    list.innerHTML = "<p>No history available.</p>";
  }
}
