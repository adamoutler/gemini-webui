# Gemini WebUI - Project Standards & Methodology

This document outlines the architectural standards and refactoring methodology established for this project to ensure long-term legibility, maintainability, and security.

## 🏗️ Architectural Principles

1.  **Module-Level Documentation (`GEMINI.md`)**: Every major directory must contain a `GEMINI.md` file. This file acts as a local manifest explaining:
    - **Purpose**: What the module does.
    - **Internal Dependencies**: What other parts of the project this module imports.
    - **External Dependencies**: What other modules or external systems rely on this module.
2.  **Explicit Naming over Ambiguity**: Avoid "fake" or "temp" prefixes for stable components. Use "mock" for testing simulators (e.g., `mock_gemini_cli.py`) and descriptive names for production routes.
3.  **Logical Routing**: All Flask blueprints and route handlers should reside within the `src/routes/` directory to maintain a clean separation between the application's entry point (`app.py`), core logic (`src/`), and its external interface.

## 🛠️ Refactoring Methodology

When performing refactors for legibility:

1.  **Surgical Renaming**: Use `git mv` to preserve history and update all string references (imports, comments, paths) across the entire codebase.
2.  **Dependency Mapping**: Before moving or renaming a file, map its usage using `grep` or `codebase_investigator` to ensure no breaks in dynamic execution (like shell script wrappers).
3.  **Verification Cycle**:
    - Perform the refactor.
    - Run unit tests (`pytest tests/unit`) with `PYTHONPATH=.`.
    - Verify E2E flows if the change affects the frontend/backend interface.

## 🧪 Testing Standards

- **Unit Tests**: Located in `tests/unit/`. Focus on isolated logic in `session_manager.py`, `utils.py`, and `routes/`.
- **E2E Tests**: Located in `tests/e2e/`. Uses Playwright to verify full user flows, including mobile viewport simulations and SSH multiplexing.
- **Mocks**: Use `src/mock_gemini_cli.py` for high-fidelity simulation of the terminal environment without requiring a real Gemini CLI installation.

## 🛡️ Security & Integrity Mandates

As a project focused on secure terminal access, the following security invariants must be maintained:

1.  **Credential Protection**: Never log, print, or commit secrets, API keys, or sensitive credentials. Rigorously protect `.env` files, `.git`, and system configuration folders.
2.  **Paranoid Input Validation**: Trust absolutely nothing from the network or user input. Perform strict bounds checking, sanitization, and type validation (e.g., using `shlex.quote` for shell arguments).
3.  **Secure Component Communication**: All IPC and SocketIO communication should be authenticated and scoped to the specific session.
4.  **Auditability**: Every major architectural pivot or security change should be documented in the corresponding `GEMINI.md` and verified with a regression test.

## 🚀 Future Incarnations

When resuming work or onboarding new agents:

1.  Read the root `GEMINI.md` and then drill down into specific module `GEMINI.md` files for context.
2.  Maintain the established pattern of modularity—if a new feature is added, create a corresponding route in `src/routes/` and document it.
3.  Always verify that `pytest` passes before pushing changes.
4.  The job isn't done until the commit/push, and related tickets are closed. Don't wait or ask for permission to do these things.

## 📋 Ticket Transition & QA Gate Expectations

When you transition a ticket to done (via `complete_work` or `transition_ticket`), expect the following:

1. **Immediate Feedback**: You will receive a certification report from the `reality-checker` in the `additional_context`.
2. **Kanban Updates**: The kanban ticket will have a duplicate copy of this same information.
3. **Closing Requirements**: The instructions within the ticket will contain exactly what is required for you to close the ticket.
4. **Evaluation**: The `reality-checker` will receive your comment when you `update_ticket` or `complete_work` and evaluate it as part of the checks.

**Professional Communication Protocol:**

- Act professionally. Do not use excessive exclamation points or overly enthusiastic formatting (e.g., "READY!!!111!!1one!shift+1!!!11!exclamation point!").
- Treat the interaction like a conversation with a strict coworker who demands pictures and logs.
- Keep it concise: "I have provided the following evidence: ./docs/qa/myfile.md and ./docs/qa/myfile.png."

**Mandatory Checklist for Completion:**

1. Commit your changes.
2. Push to the remote branch.
3. Pass all CI checks.
4. Provide the necessary certification materials (screenshots, logs, etc.) to prove the work is completed.
