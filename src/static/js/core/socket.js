import { debugLog } from "./api.js";
import { EventBus } from "./event-bus.js";

let globalSocket = null;

export function getGlobalSocket() {
  if (!globalSocket) {
    globalSocket = io.connect(globalThis.location.origin, {
      auth: {
        csrf_token: document
          .querySelector('meta[name="csrf-token"]')
          ?.getAttribute("content"),
      },
      path: "/socket.io",
      transports: ["websocket", "polling"],
      reconnection: true,
      reconnectionDelay: 1000,
      reconnectionDelayMax: 5000,
      reconnectionAttempts: Infinity,
    });

    globalSocket.on("connect", () => {
      debugLog("Global socket connected");
      EventBus.emit("SOCKET_CONNECTED");
    });

    globalSocket.on("disconnect", () => {
      debugLog("Global socket disconnected");
      EventBus.emit("SOCKET_DISCONNECTED");
    });

    globalSocket.on("connect_error", async (error) => {
      if (error && error.message === "invalid_csrf") {
        EventBus.emit("SOCKET_CSRF_ERROR");
        console.debug("Global socket CSRF token expired. Refreshing token...");
        try {
          const newToken = await refreshCsrfToken();
          if (newToken) {
            globalSocket.auth = {
              csrf_token: newToken,
            };
            // Adding a small delay to avoid tight looping
            setTimeout(() => globalSocket.connect(), 1000);
          }
        } catch (err) {
          console.error("Failed to refresh CSRF on connect_error", err);
        }
      }
    });

    globalSocket.on("sync-tabs", (serverTabs) => {
      EventBus.emit("syncTabs", [serverTabs]);
    });

    globalSocket.on("session-terminated", (data) => {
      debugLog("Session terminated via global socket:", data.tab_id);
      EventBus.emit("closeTab", [data.tab_id, null, true]);
    });

    globalSocket.on("sessions_updated", (payload) => {
      console.log("Sessions updated payload:", payload);
      if (payload && payload.data && payload.data.output) {
        const sessions = [];
        const regex =
          /^\s*(\d+)\.\s+(.+?)\s+\(([^)]+)\)(?:\s+\[(.*?)\])?\s*$/gm;
        for (const matchArr of payload.data.output.matchAll(regex)) {
          sessions.push({
            id: matchArr[1],
            name: matchArr[2],
            meta: matchArr[3],
            uuid: matchArr[4],
          });
        }

        import("./state.js").then(({ globalState }) => {
          globalState.tabs.forEach((t) => {
            console.log("Checking tab:", t.id, t.state, t.session);
            if (
              t.state === "terminal" &&
              t.session &&
              (t.session.resume === "new" || /^\d+$/.test(t.session.resume))
            ) {
              const match = sessions.find(
                (s) => s.uuid === t.id || s.id === t.session.resume,
              );
              console.log("Found match for tab:", match);
              if (match && match.uuid) {
                if (t.session) {
                  t.session.resume = match.uuid;
                }
                const socket = getGlobalSocket();
                if (socket && socket.connected) {
                  socket.emit("update_resume", {
                    tab_id: t.id,
                    resume: match.uuid,
                  });
                }
                EventBus.emit("saveTabsToStorage", []);
                localStorage.setItem("geminiResume", match.uuid);
                console.log("Set geminiResume to:", match.uuid);
              }
            }
          });

          const activeTab = globalState.tabs.find(
            (t) => t.id === globalState.activeTabId,
          );
          if (activeTab && activeTab.state === "launcher") {
            const id = activeTab.id;
            const container = document.getElementById(id + "_instance");
            if (
              container &&
              container.querySelector(".launcher") &&
              payload.host
            ) {
              const conn = payload.host;
              const sessionListId = `${id}_sessions_${conn.label.replace(
                /[^a-z0-9]/gi,
                "",
              )}`;
              import("./session-manager.js").then(({ fetchSessions }) => {
                fetchSessions(id, conn, sessionListId, false, true, true);
              });
            }
          }
        });
      }
    });
  }
  return globalSocket;
}
