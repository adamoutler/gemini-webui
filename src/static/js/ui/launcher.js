import { debugLog, escapeHtml, customFetch } from "../core/api.js";
import { getGlobalSocket } from "../core/socket.js";
import { fetchSessions } from "../core/session-manager.js";
import { globalState } from "../core/state.js";
import { EventBus } from "../core/event-bus.js";

export const HostStateManager = {
  states: {},
  updateState: function (label, isSuccess) {
    if (!this.states[label])
      this.states[label] = {
        failures: -1,
      };
    if (isSuccess) {
      this.states[label].failures = 0;
    } else {
      if (this.states[label].failures < 0) this.states[label].failures = 2;
      else this.states[label].failures++;
    }
    return this.states[label].failures;
  },
  getIndicator: function (failures) {
    if (failures === 0) return "🟢";
    if (failures === 1) return "🟡";
    if (failures < 0) return "⚪";
    return "🔴";
  },
  getStatusClass: function (failures) {
    if (failures === 0) return "connected";
    if (failures === 1) return "degraded";
    if (failures < 0) return "offline";
    return "error";
  },
  renderHealthUI: function (tabId, label, failures) {
    const indicatorId = `${tabId}_health_${label.replace(/[^a-z0-9]/gi, "")}`;
    const el = document.getElementById(indicatorId);
    if (el) {
      el.innerText = this.getIndicator(failures);
      el.dataset.status = this.getStatusClass(failures);
    }
  },
  triggerPulse: function (tabId, label) {
    const pulseId = `${tabId}_pulse_${label.replace(/[^a-z0-9]/gi, "")}`;
    const pulseEl = document.getElementById(pulseId);
    if (pulseEl) {
      pulseEl.classList.remove("pulsing", "superbright");
      const _reflow = pulseEl.offsetWidth;
      requestAnimationFrame(() => {
        pulseEl.classList.add("pulsing", "superbright");
      });
    }
  },
  updateHealth: function (tabId, label, isSuccess, shouldPulse = false) {
    const prevClass = this.getInitialStatusClass(label);
    debugLog("UPDATE HEALTH CALLED WITH " + isSuccess);
    const failures = this.updateState(label, isSuccess);
    const newClass = this.getStatusClass(failures);
    this.renderHealthUI(tabId, label, failures);
    if (shouldPulse || prevClass !== newClass) {
      this.triggerPulse(tabId, label);
    }
  },
  getInitialIndicator: function (label) {
    if (!this.states[label]) return "⚪";
    return this.getIndicator(this.states[label].failures);
  },
  getInitialStatusClass: function (label) {
    if (!this.states[label]) return "offline";
    return this.getStatusClass(this.states[label].failures);
  },
};

export function updateStatus(target, dir) {
  const statusEl = document.getElementById("connection-status");
  if (target === "local" || target === "picker" || !target) {
    statusEl.innerText = target === "picker" ? "launcher" : "local";
    statusEl.style.color = "#2472c8";
  } else {
    const host = target.split("@").pop();
    statusEl.innerText = "ssh: " + host + (dir ? ":" + dir : "");
    statusEl.style.color = "#0dbc79";
  }
}

export function updatePageTitle(title) {
  if (title) {
    document.title = title;
  }
}
