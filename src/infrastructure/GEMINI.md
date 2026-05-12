# src/infrastructure Module

## Purpose

The `src/infrastructure` directory is the foundational bedrock for system resilience, process management, and concurrency safety within the Gemini WebUI. It provides the low-level OS interfaces necessary to manage child processes (like PTYs and SSH sessions) reliably in a highly concurrent, green-thread (Eventlet) environment. It ensures that system resources are never leaked and that rogue processes are aggressively reaped.

## General Themes

- **Process Lifecycle Management**: It is the single source of truth for spawning, tracking, and safely terminating OS-level processes.
- **Resource Safety & Resilience**: Implements aggressive cleanup strategies to prevent resource exhaustion, including zombie process reaping and orphaned session garbage collection.
- **Concurrency Bridging**: Handles the complexities of mixing blocking OS calls (like `subprocess.run`) with the non-blocking `eventlet` loop.
- **Defensive Programming**: Employs techniques like monkey-patching and signal handling (e.g., using process groups, `killpg`, `SIGKILL`) to guarantee termination even when standard protocols fail or when processes enter an unrecoverable state.

## Module Contracts & APIs

### `process_manager.py`

This module encapsulates all process-related operations.

- **`apply_subprocess_monkey_patch()`**

  - **Contract**: Protects the application from blocking `subprocess.run` calls leaking processes if the executing greenlet is killed (e.g., via a timeout).
  - **Behavior**: Overrides the standard library `subprocess.run` with a custom implementation that tracks the `Popen` object in the global `shared_state.abandoned_pids` set. If an `eventlet.timeout.Timeout` is caught, it guarantees the spawned process (and its children, via process groups) is killed before re-raising the timeout.

- **`add_managed_pty(pid, meta)`**

  - **Contract**: Registers a newly created PTY process for lifecycle tracking.
  - **Behavior**: Adds the PID and associated metadata to a global tracking dictionary. This allows the system to differentiate between actively managed terminal sessions and abandoned/rogue processes.

- **`kill_and_reap(pid_to_kill)`**

  - **Contract**: Forcefully and reliably terminates a specific process and all its children.
  - **Behavior**:
    - Retrieves the Process Group ID (PGID) for the given PID.
    - Sends `SIGTERM` followed by a brief wait, and then `SIGKILL` if the process persists.
    - Actively calls `os.waitpid` with `WNOHANG` to ensure the OS process table is cleared (preventing zombies).
    - Includes extensive `try/except` blocks to handle race conditions where the process might have died organically.

- **`zombie_reaper_task(app)`**

  - **Contract**: A global, background garbage collector for processes.
  - **Behavior**: Periodically scans `shared_state.abandoned_pids` and the managed PTY list. If it detects processes that are no longer associated with an active WebUI session, it invokes `kill_and_reap`.

- **`cleanup_orphaned_ptys(app)`**
  - **Contract**: Reclaims resources from sessions that have been abandoned by the user.
  - **Behavior**: Iterates through active sessions in the `session_store`. If a session has no connected clients and has exceeded the `SESSION_TTL_SECONDS` (e.g., 20 minutes), it destroys the session and kills the underlying PTY process.

## Internal Dependencies

- **`src/shared_state.py`**: Utilizes global structures like `abandoned_pids` to communicate process state across greenlets.
- **`eventlet`**: Heavily relies on eventlet for timeouts, sleeping, and green-thread concurrency.

## External Dependencies

- **`src/services/terminal_service.py`**: Calls `add_managed_pty` when spawning new terminals.
- **`src/services/session_store.py`**: Invokes `kill_and_reap` when destroying sessions or evicting them from the cache.
- **`src/app.py`**: Initializes the infrastructure by calling `apply_subprocess_monkey_patch` and starting the background tasks like `zombie_reaper_task` during application startup.
