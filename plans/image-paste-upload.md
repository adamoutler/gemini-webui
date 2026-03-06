# Feature: Image Paste and Automatic Upload

## Description
We need to implement the ability to paste pictures directly into the terminal window and have them automatically upload and append to the prompt.
Additionally, we need to resolve a bug where users encounter "Failed to share: CSRF token missing or incorrect" and "Upload failed: undefined" after the backend restarts (e.g. via a zero-downtime deployment or idle session reconnect).

## Details

### 1. Paste-to-Upload Pictures
- **Frontend Action**: Listen for the `paste` event on the terminal instance (`xterm.js` or the document/container). 
- If the pasted data contains an image (e.g., `event.clipboardData.items`), intercept the paste and extract the file.
- Automatically trigger an upload using the existing `/api/upload` endpoint logic.
- Upon successful upload, automatically send a command to the terminal prompt: `> I uploaded @<filename>`. 
- **Note**: The user assumes the files will be temporary and the AI can handle moving them later, so saving to the standard upload location (`@tmp/` or just the filename returned by the API) is fine.

### 2. Fix CSRF Token Missing/Incorrect Bug
- **Bug Context**: The user sees "Failed to share: CSRF token missing or incorrect" and "Upload failed: undefined" when trying to upload. This happens when the backend connection drops and reconnects (e.g., during a deployment/restart) without a full page refresh. The old CSRF token in the `<meta name="csrf-token">` tag becomes invalid because the Flask server generated a new `SECRET_KEY` or the session expired.
- **Resolution Strategy**: 
  - Add an API endpoint to fetch a fresh CSRF token.
  - Or, intercept 400/403 CSRF errors in the UI, prompt a silent token refresh, and retry the request.
  - Alternatively, if the WebSocket re-establishes connection and detects a server restart, it could trigger a request to refresh the CSRF token in the DOM.

## Definition of Done
1. **Paste Upload**: A user can copy an image to their clipboard and paste it while the terminal is focused. The image uploads successfully and the terminal receives the input `> I uploaded @<filename>`.
2. **CSRF Resiliency**: If the server restarts and the client auto-reconnects, subsequent file uploads or session shares do not fail with "CSRF token missing or incorrect".
3. **Tests**: 
   - A unit/UI test must be added to verify image pasting.
   - A unit/UI test must be added to verify that a file upload or share succeeds even after the backend `SECRET_KEY` has rotated or session was cleared, without requiring a manual page reload.
