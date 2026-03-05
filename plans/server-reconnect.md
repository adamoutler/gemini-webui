# Feature: Auto-reconnect after server restart

**Details:**
Currently, when the Gemini WebUI server restarts (e.g. during a deployment like `git p`), the WebSocket connection drops. The client seems to get an error and stops attempting to reconnect after a while (or immediately), leaving the user with a dead terminal until they manually refresh the page.

We need to implement a robust auto-reconnection strategy in `src/static/app.js`:
- Upon `socket.on('disconnect')`, implement a retry loop with exponential backoff (or a fixed interval of e.g., 2 seconds).
- The retry should continue for at least 30-60 seconds to account for the ~20s server restart time.
- Display a non-intrusive "Reconnecting..." indicator in the UI (perhaps on the `#connection-status` element) while attempting to reconnect.
- Once reconnected, the client should attempt to re-establish the active PTY sessions or at least gracefully notify the user that they can resume.

**Test Recommendations:**
1. Unit test in Playwright (`tests/test_socket.py` or similar) that manually stops the Flask server or forces a socket disconnect, waits 10 seconds, restarts it, and verifies the UI shows a reconnected state.
2. Verify that the UI indicator correctly displays "Disconnected" or "Reconnecting...".

**Definition of Done:**
- When the backend server restarts, the frontend client automatically attempts to reconnect and succeeds once the server is back up.
- The user does not have to manually refresh the browser page.
