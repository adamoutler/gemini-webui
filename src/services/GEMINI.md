# src/services Module

## Purpose

The `src/services` directory houses the core business logic and orchestration engine of the Gemini WebUI. It abstracts the complexities of the underlying infrastructure (processes, sockets, file systems, SQLite databases) into clean, logical APIs that the application routes and gateways can consume. It is the brains of the operation.

## General Themes

- **SSH Multiplexing**: Heavily utilizes SSH multiplexing (ControlMaster/ControlPath) to drastically reduce connection latency when discovering or interacting with remote sessions.
- **Background Orchestration**: Manages continuous background tasks (like `session_poller`) to maintain an eventually-consistent cache of global system state without blocking request threads.
- **Resource Limits & Safeties**: Implements strict limits (e.g., 2-second timeouts on SSH commands, 1MB limits on scrollback buffers) to guarantee application stability even when target hosts are unresponsive or malicious.
- **Separation of Storage & Logic**: Clearly separates persistence layers (like `session_store.py` and `schedule_manager.py`) from execution layers (like `process_engine.py`).

## Module Contracts & APIs

### `process_engine.py` & `terminal_service.py` (Execution Layer)

- **Contract**: Responsible for constructing shell commands, establishing connections, and spawning the actual PTY processes.
- **`SSHConnectionManager`**: The core utility for interacting with remote hosts. It handles the creation of multiplexed sockets and execution of `tmux ls` commands to discover sessions.
- **`TerminalService.start_session()`**: The primary factory method for creating new `Session` objects. It determines the correct execution strategy (local shell, SSH, container attachment) based on the session parameters.

### `session_store.py` & `session_poller.py` (Lifecycle & Discovery)

- **Contract**: Maintains the global registry of all active sessions and synchronizes this state with external hosts.
- **`SessionManager`**: A singleton that tracks live `Session` objects in memory. It provides methods to retrieve, evict, and list sessions.
- **`SessionPersistenceManager`**: Handles saving session metadata across server restarts (typically to disk or a localized database).
- **`SessionPollerManager`**: A background task manager that periodically queries all known `Host` configurations to populate the `SessionManager`'s cache.

### `automation_bridge.py` & `schedule_manager.py` (Automation Subsystem)

- **Contract**: Manages user-defined tasks and schedules, executing them at appropriate times.
- **`ScheduleManager`**: The persistence layer (SQLite) for storing cron expressions, target commands, and historical run data.
- **`AutomationBridge`**: The execution engine that evaluates cron expressions, triggers jobs via `TerminalService`, and records the output/status back to the `ScheduleManager`.

### `remote_fs.py` (File Operations)

- **Contract**: Provides high-level APIs for interacting with remote file systems.
- **Behavior**: Abstracted over SFTP, this module provides `upload_to_remote` and `download_from_remote`, ensuring safe transport of workspace files.

## Internal Dependencies

- **`src/infrastructure/process_manager.py`**: The execution layer heavily relies on this for low-level process spawning and zombie prevention.
- **`src/models/session.py`**: The lifecycle layer owns and manages instances of these models.
- **`eventlet`**: Relies on greenlets for background polling and timeouts.

## External Dependencies

- **`src/routes/*`**: The primary consumers of these services (e.g., `api.py` calling the `ScheduleManager`, `terminal.py` calling `SessionManager`).
- **`src/gateways/terminal_socket.py`**: Interfaces with `TerminalService` for restarting/spawning PTYs and `SessionManager` for reclamation.
