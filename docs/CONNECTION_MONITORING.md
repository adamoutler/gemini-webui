# Connection Monitoring and Startup Flow

This document outlines the intended flow and architecture for connection monitoring, session management, and terminal startup within the Gemini WebUI. This is a core feature of the application; adherence to this flow is critical to prevent regressions and ensure a stable user experience.

## 1. The Connection Monitor

The connection monitor runs constantly in the background. It is responsible for tracking the status of all configured hosts and updating the backend state. This includes monitoring the health/reachability of the connection itself, as well as retrieving the list of active and historical sessions for each connection.

## 2. Connection Objects and Session Tracking

Within each connection object, the backend tracks a list of available Gemini sessions. The data structure for these sessions generally includes:

| Connection Number | Description / Message          | Last Used    | UUID                   |
| :---------------- | :----------------------------- | :----------- | :--------------------- |
| e.g., 1           | "please run a unit test on..." | 22 hours ago | `xxxx-xxx-xxxxx-xxxxx` |

## 3. UI: Connection Selection Tab

The "Select a Connection" interface displays all configured connections and their associated sessions.

- **Polling:** Information is pulled from the backend on a regular interval.
- **Visual Feedback:** Upon receiving an update (whether the data changed or not), a "superbright" flash animation occurs on the connection cards to indicate a state refresh.
- **Status Indicators:** During the update flash, the connection status indicator is refreshed (e.g., Green for connected, Red for disconnected, Yellow for degraded/connecting, Grey for unknown/disabled). The list of available sessions is also synchronized with the backend.

## 4. Starting a New Connection (New Session)

When a user clicks to start a completely new session on a host:

1. Establish the SSH connection to the target host.
2. Execute the `gemini` CLI command in the shell.
3. **Interim Resume State:** Immediately update the UI tab's internal `resume` tracking property with the _highest currently known connection number + 1_. For example, if the monitor reported the highest session number was 4, the tab's resume target becomes `5`. If an unexpected restart or disconnect occurs immediately, the system will attempt to recover using `gemini -r 5`.
4. **Permanent Resume State:** On the next successful polling update from the connection monitor, the tab's `resume` property is updated from the temporary integer ID to the actual newly generated `UUID`. Any subsequent restarts will then use `gemini -r <actual UUID>`.

## 5. Resuming the Last Connection

When a user chooses to rapidly resume the most recent session:

1. Establish the SSH connection to the target host.
2. Execute `gemini -r` (which tells the CLI to default to the last active session).
3. Update the tab's `resume` property with the actual last recorded `UUID` known to the backend. If a restart occurs, the system will reliably use `gemini -r <UUID>`.

## 6. Resuming a Specific Session

When a user selects a specific historical session from the list to resume:

1. Establish the SSH connection to the target host.
2. Execute `gemini -r <UUID>`.
3. Update the tab's `resume` property with that specific `UUID` to ensure resilience against unexpected disconnects.

## 7. Polling Updates & Data Volatility

During normal operation, the backend connection monitor continuously polls the remote hosts to keep the UI in sync.

- **Volatility of Integers:** Session numbers (integers like 1, 2, 3) are highly volatile. Old sessions can be pruned automatically due to age, maximum session constraints, or manual user commands (e.g., `gemini --delete-sessions`). This pruning causes the integer IDs to shift or become invalid.
- **Constancy of UUIDs:** Because integer IDs are volatile, the **UUID** is the only reliable, constant identifier for a session over time. The application must always prioritize transitioning from interim integer IDs to strict UUIDs (as described in the startup flows) to ensure sessions can be accurately recovered regardless of background pruning.
