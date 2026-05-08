# GEMWEBUI-407: Terminal Buffer Redraw and Firehose Mitigation - Continuity Document

## 1. Executive Summary

This document serves as the historical record and continuity context for the `gemini-webui` terminal rendering issues resolved under GEMWEBUI-407. The user reported that the terminal would flash black, jitter, and continuously scroll-jack to the bottom during high-throughput text bursts (e.g., `cat /dev/urandom` or large log dumps). The symptoms were exacerbated by larger text sizes and longer messages.

## 2. Architectural Diagnosis

Following a parallel investigation by the `codebase_investigator`, `frontend-developer`, `ux-architect`, `backend-architect`, and `terminal-integration-specialist`, five root causes were identified:

1. **The Backend Firehose (Event Loop Starvation):**
   The `session_output_reader` in `src/gateways/terminal_socket.py` was reading up to 20KB from the PTY and emitting it via Socket.IO in a tight loop without yielding. This starved the Python Eventlet hub, preventing the server from answering Socket.IO `ping` frames.
2. **Socket Flapping & Reclaim Loop:**
   Because the event loop was starved, the frontend timed out and disconnected. Upon reconnecting a fraction of a second later, the backend `pty_restart` handler assumed the session was being reclaimed and forcefully dumped the entire 1MB history buffer to the client.
3. **The "Black Flash" (Explicit Clear):**
   In `src/static/js/terminal/ui.js`, the `handleConnect` function explicitly called `tab.term.clear()` every time the WebSocket connected. This caused a visible black flash before the backend buffer dump arrived.
4. **Dimension Artifacts (The Resize Typo):**
   The frontend emitted `resize` on window changes, but the backend listened for `pty-resize`. The Linux PTY was stuck at 80x24. When long lines arrived, Linux forced hard wraps at 80 columns, causing staggered, broken text artifacts on the frontend.
5. **Scroll Yanking & UI Jitter:**
   Unthrottled cursor alignment events in mobile UI and aggressive scroll-to-bottom heuristics trapped the user in "limbo" during these bursts.

## 3. Surgical Mitigations Applied

To stabilize the system without introducing massive architectural overhauls, the following three fixes were deployed:

### A. The Yield Throttle

**File:** `src/gateways/terminal_socket.py`
**Action:** Added `socketio.sleep(0.001)` inside the `data_ready` block of `session_output_reader`.
**Result:** The backend now cooperatively yields to the eventlet hub after every chunk. The browser never freezes, Socket.IO never drops, and the flapping loop is broken.

### B. The Dimension Typo Fix

**File:** `src/static/js/terminal/ui.js`
**Action:** Changed the event emission in `fitTerminal` from `resize` to `pty-resize`.
**Result:** The backend PTY now correctly matches the frontend window size, completely eliminating the staggered text wrapping artifacts.

### C. Removal of Redundant Clear

**File:** `src/static/js/terminal/ui.js`
**Action:** Removed the _second_ redundant `tab.term.clear()` call inside `handleConnect`.
_Critical Note:_ The first `clear()` call was intentionally preserved. If it were removed, the backend's forced 1MB buffer dump upon reconnect would append to the existing screen text, duplicating the entire history.

## 4. QA and Telemetry Integration

As mandated by the `evidence-collector` QA Agent, the following telemetry and tests were added:

1. **Frontend Telemetry:**
   - **Main Thread Block Detector:** A `requestAnimationFrame` loop now monitors UI freezes and logs `[PERF_ALERT]` if frames drop below 200ms.
   - **Socket Flap Tracker:** A disconnect listener now logs `[SOCKET_FLAP]` and tracks reconnect counts.
2. **E2E Stability Test (`tests/e2e/test_firehose_stability.py`):**
   - Blasts the terminal with `seq 1 20000; echo 'DONE_FIREHOSE'`.
   - Programmatically traps browser console logs.
   - Asserts that 0 `[SOCKET_FLAP]` events occurred during the load.
   - Rapidly resizes the viewport under load and captures visual proof.
3. **QA Artifacts Generated:**
   - `docs/qa/firehose-stress-console.png`
   - `docs/qa/terminal-resize-before.png`
   - `docs/qa/terminal-resize-after.png`
   - `docs/qa/test-results.json`
   - `docs/qa/backend-yield-logcat.txt`

## 5. Future Roadmap: "Delta Syncing"

**WARNING TO FUTURE AGENTS:** Do not attempt to remove the remaining `tab.term.clear()` call in `ui.js` without first implementing **Delta Syncing**.

Currently, on reconnect, the backend (`pty_restart`) dumps the full buffer. To fully modernize the connection logic, the architecture must be upgraded:

1. The frontend must track a `bytesReceived` or `lastLineIndex` cursor.
2. On reconnect, the frontend must send this cursor to the backend.
3. The backend must only emit buffer data _newer_ than that cursor.
   Once Delta Sync is implemented, the final `clear()` can be removed safely, resulting in seamless, invisible reconnections.
