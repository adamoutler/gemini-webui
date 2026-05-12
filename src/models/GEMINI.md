# src/models Module

## Purpose

The `src/models` directory defines the core data structures and stateful objects that represent the business domain of the application. It establishes the architectural foundation for how data is organized in memory, how it is serialized, and how it manages underlying system resources.

## General Themes

- **Stateful Resource Wrappers**: Models in this system are not just passive data containers; they actively manage system resources (like File Descriptors and PIDs) and ensure they interact safely with the async event loop.
- **Contract Definition**: This directory establishes the formal schema contracts (e.g., for automation jobs) that the rest of the application should rely upon, even if the underlying storage layer uses dynamic dictionaries.
- **Data Encapsulation**: Encapsulates complex logic within the object itself (e.g., incremental UTF-8 decoding, bounded scrollback buffers) rather than leaking it into the service layer.

## Module Contracts & APIs

### `session.py` (Active State Models)

This file defines the `Session` class, the most critical model in the application.

- **`Session` Class**
  - **Contract**: Represents a live terminal multiplexing instance. It bridges a pseudo-terminal (PTY) file descriptor with the logical state needed by the web application.
  - **Behavior/Requirements**:
    - **Non-Blocking I/O**: The constructor MUST configure the provided file descriptor (FD) using `os.set_blocking(fd, False)`. This is an invariant required to prevent deadlocks in the `eventlet` hub.
    - **Scrollback Management**: Uses a `collections.deque` with a `maxlen` (typically 1MB limit) to store the terminal output history. This is the primary defense against memory exhaustion.
    - **UTF-8 Safety**: Implements an `IncrementalDecoder` to handle multi-byte characters that might be split across read operations from the PTY, ensuring the browser always receives valid unicode.
  - **Key Methods**:
    - `append_buffer(data)`: Safely decodes and adds bytes to the scrollback queue.
    - `get_buffer_content()`: Returns the full history for UI reconstruction.
    - `update_last_seen()`: Updates the timestamp used by the garbage collector.
    - `to_dict()`: Serializes non-sensitive metadata for API responses.
  - **Usage**: Instantiated by `src/services/terminal_service.py` and managed by `src/services/session_store.py`.

### `schedule.py` (Schema Definition Models)

This file defines the data structures for the automation subsystem.

- **`Schedule` & `AutomationJob` Dataclasses**
  - **Contract**: Defines the canonical structure, types, and required fields for automation configurations and historical job runs.
  - **Behavior**: They provide type hints and structural guarantees for data moving between the UI, the scheduler, and the database.
  - **Usage**: While the current SQLite implementation in `ScheduleManager` might work with raw row dictionaries for expediency, these models act as the formal interface contract. Future refactors should instantiate these objects when moving data across boundaries.

## Internal Dependencies

- Standard Library (`collections.deque`, `codecs`, `os`, `fcntl`): Relies heavily on native Python modules for low-level resource management and efficient data structures.

## External Dependencies

- **`src/services/session_store.py`**: Acts as the repository and lifecycle manager for `Session` instances.
- **`src/services/terminal_service.py`**: Acts as the factory that creates `Session` instances after spawning processes via `process_manager`.
- **`src/routes/api.py`**: Consumes model serialization methods (like `to_dict`) to render HTTP responses.
