# Zombie Process Hunting Log

## Issue Overview

- **Symptom:** `ssh` processes are turning into zombies (`<defunct>`).
- **Parent Process:** `ps -f -p <pid>` indicates that the zombie processes have their PPID set to `python src/app.py` (the main Gemini WebUI application process).
- **Reproduction:** Tests in `tests/reproduce_zombie_v2.py` interact with connection UI (e.g., clicking "Start New", rapidly closing/reopening tabs), which triggers backend processes causing the `ssh` leak.

## Technical Discoveries

1. **Subprocess Management in `src/app.py`:**

   - The application manages PTY processes using `pty.fork()` and keeps track of them in a `managed_ptys` set.
   - A background thread (`zombie_reaper_task`) runs periodically and calls `os.waitpid(pid, os.WNOHANG)` strictly on PIDs inside `managed_ptys`.

2. **`ssh` Spawn Points:**

   - `ssh` is NOT directly spawned by `pty.fork()` during a typical local interaction.
   - It is spawned by `subprocess.run()` across multiple components (e.g., `process_manager.py`'s `fetch_sessions_for_host`, `build_terminal_command`, and API checks).
   - In `src/app.py`, the `subprocess.run` function is explicitly patched to use `eventlet.green.subprocess.run`.

3. **Why Do Zombies Occur?**

   - **Race Condition in `kill_and_reap`**: When "Restart" or other cleanup operations occur, `kill_and_reap(pid)` was sending `SIGKILL` and then immediately calling a non-blocking `os.waitpid(pid, os.WNOHANG)`. Because the kernel takes a few milliseconds to process `SIGKILL` and terminate the process, this immediate wait almost always returned `(0, 0)` (meaning the process hasn't exited yet). The function then permanently discarded the PID from `managed_ptys`. Because it was no longer in the tracking set, `zombie_reaper_task` never attempted to reap it again, leaving a permanent zombie once it finally died.
   - **Green Thread Interruption:** If a user cancels a request, the Flask/Eventlet framework kills the greenlet. If the greenlet was blocking on `subprocess.run()`, the `Popen` object is destroyed before its `wait()` completes.

4. **Addressing the "Node App" Idea:**
   - While deploying a companion Node application on remote systems is possible, the zombie issue is entirely a **local process management issue**. The zombies were local `ssh` client processes spawned by the Python backend that were not correctly `wait()`-ed upon termination. A remote Node helper wouldn't solve the failure of the local python script to properly reap its local children.

## Resolutions Applied

- Fixed `kill_and_reap` in `src/app.py` by removing the immediate `managed_ptys.discard(pid)` step. Now, it sends the `SIGKILL`, optionally attempts an instantaneous reap, and leaves the PID in the tracking set. The main `zombie_reaper_task` daemon will safely reap and clean up the tracking set once the process actually finishes terminating.

## Note on Pre-existing Zombies

- Any `<defunct>` processes that were spawned by `src/app.py` (e.g., PID 6749) _before_ the fix was applied will remain as zombies until their parent process (6749) is restarted. When a parent process terminates, all its zombie children are inherited by `init` (PID 1) and automatically reaped by the OS.

## Ticket Update (GEMWEBUI-320)

I have implemented the fixes to resolve the zombie process leak:

1. Fixed `kill_and_reap` to conditionally discard the PID only if the non-blocking wait successfully reaps it.
2. Implemented `safe_subprocess_run` wrapper to catch `GreenletExit` and track orphaned PIDs in a global `abandoned_pids` set.
3. Updated `zombie_reaper_task` to iterate over both `managed_ptys` and the new `abandoned_pids` list.
4. Resolved the `no such user: 'node'` and `style-src` CSP errors that were flagged in the dash logs.
5. Fixed WebGL dimensions error in frontend `src/static/app.js`.

**Note**: The `tests/e2e/test_ctrl_enter.py` timeout is an existing architectural race condition in the main branch's testing harness (where `is_fake=False` for local connections bypasses the `GEMINI_WEBUI_HARNESS_ID` injection, causing a 15-second blocking query in the mock). I recommend opening a separate ticket for this test harness issue.
