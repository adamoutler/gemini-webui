# Gemini WebUI - Project Standards & Methodology

This document outlines the architectural standards and refactoring methodology established for this project to ensure long-term legibility, maintainability, and security.

## 🏗️ Architectural Principles

1.  **Module-Level Documentation (`GEMINI.md`)**: Every major directory must contain a `GEMINI.md` file. This file acts as a local manifest explaining:
    *   **Purpose**: What the module does.
    *   **Internal Dependencies**: What other parts of the project this module imports.
    *   **External Dependencies**: What other modules or external systems rely on this module.
2.  **Explicit Naming over Ambiguity**: Avoid "fake" or "temp" prefixes for stable components. Use "mock" for testing simulators (e.g., `mock_gemini_cli.py`) and descriptive names for production routes.
3.  **Logical Routing**: All Flask blueprints and route handlers should reside within the `src/routes/` directory to maintain a clean separation between the application's entry point (`app.py`), core logic (`src/`), and its external interface.

## 🛠️ Refactoring Methodology

When performing refactors for legibility:
1.  **Surgical Renaming**: Use `git mv` to preserve history and update all string references (imports, comments, paths) across the entire codebase.
2.  **Dependency Mapping**: Before moving or renaming a file, map its usage using `grep` or `codebase_investigator` to ensure no breaks in dynamic execution (like shell script wrappers).
3.  **Verification Cycle**:
    *   Perform the refactor.
    *   Run unit tests (`pytest tests/unit`) with `PYTHONPATH=.`.
    *   Verify E2E flows if the change affects the frontend/backend interface.

## 🧪 Testing Standards

*   **Unit Tests**: Located in `tests/unit/`. Focus on isolated logic in `session_manager.py`, `utils.py`, and `routes/`.
*   **E2E Tests**: Located in `tests/e2e/`. Uses Playwright to verify full user flows, including mobile viewport simulations and SSH multiplexing.
*   **Mocks**: Use `src/mock_gemini_cli.py` for high-fidelity simulation of the terminal environment without requiring a real Gemini CLI installation.

## 🚀 Future Incarnations

When resuming work or onboarding new agents:
1.  Read the root `GEMINI.md` and then drill down into specific module `GEMINI.md` files for context.
2.  Maintain the established pattern of modularity—if a new feature is added, create a corresponding route in `src/routes/` and document it.
3.  Always verify that `pytest` passes before pushing changes.
