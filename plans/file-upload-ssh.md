# Epic: Massive Fix for SSH File Uploads

## Overview
The file upload functionality is fundamentally broken for SSH sessions. Currently, when a user uploads a file over an SSH connection, the system exhibits the following failure chain:
1. The file is successfully copied to the **local container workspace**.
2. The file is **never transferred** over SSH to the remote host.
3. The backend returns a `success` status regardless.
4. The frontend blindly prints `> I uploaded @filename`, tricking the user and confusing the AI because the file does not actually exist in the expected location.

This Epic provides a hyper-granular, line-by-line plan to permanently resolve this issue. **Any sub-ticket that fails verification MUST be reopened.**

---

## 🎟️ Ticket 1: Write Strict Baseline E2E Tests (MUST BE COMPLETED FIRST)
**Objective:** Prove the failure exists and create a safety net so this never happens again. We will test this by mocking the SSH backend and asserting the exact command payload.

**Action Items for Codebase Investigator & Executor:**
1. Open `tests/test_ui_upload.py`.
2. Add a new Playwright E2E test named `test_ssh_drag_and_drop_upload`.
3. In this test, simulate starting a new SSH connection (or mock the `tab.session.ssh_target` state in the browser).
4. Perform a file drag-and-drop.
5. **CRITICAL ASSERTION:** You MUST mock `subprocess.run` in the Flask backend during this test to verify that `scp` is actually called. If the backend never fires `scp` (because `ssh_target` was lost in the frontend), the test MUST FAIL.
6. Verify that the test correctly fails against the current `main` branch before proceeding to Ticket 2.

---

## 🎟️ Ticket 2: Fix Frontend State & Form Data Injection
**Objective:** Ensure that `ssh_target` and `ssh_dir` are strictly enforced and always sent to the backend. The root cause of the silent failure is often that `tab.session.ssh_target` evaluates to false/undefined on the frontend, causing `app.js` to skip appending it to the `FormData`, which makes the backend think it's a local upload.

**Action Items:**
1. Open `src/static/app.js`.
2. Locate the `uploadWorkspaceFile` function (~line 1732) and the `dropZone.addEventListener('drop')` callback (~line 1850).
3. Update the FormData logic to strictly validate SSH state:
   ```javascript
   if (tab && tab.session && tab.session.type === 'ssh') {
       if (!tab.session.ssh_target) {
           alert("SSH target is missing from session state! Upload cannot proceed.");
           return;
       }
       formData.append('ssh_target', tab.session.ssh_target);
       if (tab.session.ssh_dir) {
           formData.append('ssh_dir', tab.session.ssh_dir);
       }
   }
   ```
4. This ensures that if it is an SSH session, we NEVER silently fall back to a local upload.

---

## 🎟️ Ticket 3: Fortify Backend SCP Execution & Verification
**Objective:** The backend currently trusts that if `scp` returns `0`, the file is ready. Furthermore, if `ssh_dir` is missing, it drops the file in `~/`, which might not be where the AI is looking. We must explicitly verify the file arrived.

**Action Items:**
1. Open `src/app.py` and locate the `/api/upload` route (~line 712).
2. If `ssh_target` is present, evaluate `remote_path`. If `ssh_dir` is empty or `~`, ensure we know exactly where `remote_path` resolves.
3. Update the `subprocess.run(ssh_cmd)` (the `mkdir -p` call) to check for errors:
   ```python
   if remote_dir:
       ssh_cmd = ['ssh'] + base_ssh_args + ['--', ssh_target, f"mkdir -p {shlex.quote(remote_dir)}"]
       res = subprocess.run(ssh_cmd, capture_output=True, text=True)
       if res.returncode != 0:
           return jsonify({"status": "error", "message": f"Failed to create remote directory: {res.stderr}"}), 500
   ```
4. **The "Trust But Verify" Step:** After the `scp_cmd` succeeds, you MUST add an explicit `ssh` call to `ls` or `stat` the file on the remote machine to guarantee it exists before returning `success`.
   ```python
   verify_cmd = ['ssh'] + base_ssh_args + ['--', ssh_target, f"ls {shlex.quote(remote_path)}"]
   verify_res = subprocess.run(verify_cmd, capture_output=True)
   if verify_res.returncode != 0:
       return jsonify({"status": "error", "message": "SCP returned 0, but file verification failed on remote host."}), 500
   ```

---

## 🎟️ Ticket 4: Absolute Path UI Injection (Optional but Recommended)
**Objective:** To prevent the AI from being confused when a file is uploaded to `~` but the terminal is in `/var/www/`, the UI should inject the absolute or explicit remote path.

**Action Items:**
1. In `src/app.py` (`/api/upload`), calculate the definitive remote path string.
2. Return it in the JSON response: `return jsonify({"status": "success", "filename": definitive_remote_path})`
3. In `src/static/app.js`, ensure the injection string uses this path:
   `tab.socket.emit('pty-input', {input: \`> I uploaded @${result.filename} \`});`
4. Run all E2E tests written in Ticket 1. They MUST pass.

---
**Review & Reopen Policy:**
If at any point during Ticket 2, 3, or 4 the E2E tests fail or manual verification fails, the specific ticket MUST be reopened and re-evaluated by the Quality Control agent. Do not mark the Epic as done until a file can be dragged into an SSH session and subsequently found using `ls` in the terminal.