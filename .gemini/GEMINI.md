# Gemini WebUI: AI Orientation & Technical Documentation

Welcome, fellow Gemini. This document provides a comprehensive technical overview and orientation for working on the Gemini WebUI project.

## 1. Project Overview
The **Gemini WebUI** is a specialized, secure web-based terminal interface designed for a single user to interact with the Gemini CLI. It bridges the gap between a web browser and a pseudo-terminal (PTY) running either locally or over SSH.

### Core Mission
To provide a persistent, high-fidelity terminal experience for the Gemini CLI with enterprise-grade authentication and zero-downtime deployment.

---

## 2. Technical Architecture
The application is built using a modern, asynchronous stack:

- **Backend**: Python 3.11 with **Flask** and **Flask-SocketIO** (Eventlet mode).
- **Frontend**: **xterm.js** for terminal emulation, styled with a high-fidelity 256-color theme.
- **Communication**: Real-time bidirectional streaming via **WebSockets**.
- **PTY Management**: Python's `pty` and `fcntl` modules to fork processes and manage window dimensions.
- **Character Encoding**: Incremental UTF-8 decoding to prevent mangling of complex terminal graphics (like box-drawing characters).

### The Flow
1. User authenticates via LDAP (Active Directory).
2. Browser connects via SocketIO.
3. Backend forks a PTY running `gemini` (local) or `ssh -t ... "gemini"` (remote).
4. `ResizeObserver` on the client keeps the backend PTY dimensions in sync.
5. Standard input/output is streamed between xterm.js and the PTY.

---

## 3. Key Features

### Local vs. SSH Connectivity
- **Local**: Runs the `gemini` binary inside the container.
- **SSH**: Initiates an SSH tunnel to a target host (e.g., `192.168.1.101`) and executes Gemini there. This allows the AI to operate directly on the host filesystem.

### Resume Functionality
The UI includes a "Resume" toggle. When enabled, the Gemini process is started with the `-r` flag, allowing it to pick up previous conversation context from the state files.

### Persistence (~/.gemini)
The container environment mounts the host's `~/.gemini` directory to `/home/node/.gemini`. This is **CRITICAL** because:
1. It stores the Gemini CLI's persistent memory and configuration.
2. It allows different instances (web or local terminal) to share the same AI state.

---

## 4. Environment & Deployment

### CI/CD Pipeline (Jenkins)
The project uses a custom Jenkins pipeline defined in the `Jenkinsfile`:
- **Build Receipt System**: Reports detailed build logs to `/tmp/jenkins-receipt-gemini-webui.log` on the host.
- **Zero-Downtime**: Uses `docker buildx` to prepare images before taking down the old container.
- **Credential Injection**: Securely handles Google API keys, LDAP bind credentials, and SSH private keys.

### Deployment & Context Recovery
**Automatic Deployment Check**: When you execute `git push`, an automated Gemini CLI hook will intercept your command and append the deployment check script (`./jenkins/wait-for-receipt.sh`). You do not need to do this manually.

> [!CAUTION]
> **DEPLOYMENT VISIBILITY WARNING**: Because a `git push` triggers a zero-downtime deployment that restarts the server, **you will lose the response context of the `git push` command itself**.
> 
> **MANDATORY RECOVERY WORKFLOW**: 
> 1. Stage and commit your changes in one turn (`git add ... && git commit -m "..."`).
> 2. Before executing `git push`, explicitly state: *"Executing git push. I will lose context. When you resume, I will check the build receipt."*
> 3. **Post-Resume:** Upon waking up in a new session after a deployment, your FIRST action must be to read `/tmp/jenkins-receipt-gemini-webui.log` and run `git status` to re-orient yourself before continuing the pipeline.

### SSH Identity
The `Dockerfile` and `Jenkinsfile` work together to inject an SSH private key (`id_ed25519`) and configure `~/.ssh/config` at build time. The username is dynamically injected into `src/GEMINI.md` for user reference.

---

## 5. Development & Testing

### Project Structure
- `src/`: Core application logic, templates, and static assets.
- `tests/`: UI and logic tests.
- `jenkins/`: CI/CD helper scripts.
- `.gemini/`: AI-specific instructions and skills.

### Running Unit/UI Tests
The project uses **Pytest** and **Playwright**.
1. Ensure dependencies are installed: `pip install -r requirements.txt`.
2. Run tests: `pytest tests/test_ui.py`.
*Note: The tests use a mock Gemini binary located in `tests/mock/gemini` to verify terminal flow without consuming real API tokens.*

**Testing Mandates:**
- **Feedback Loop**: Every request must have a realtime feedback loop. For any new feature, you must add a corresponding unit test to ensure it is always tested in the future.
- **Test-Driven Reliability**: Tests are the only quality guarantee. Every functional feature MUST have a unit test.
- **Performance**: Individual tests must NEVER take longer than 10 seconds.
- **Safety**: NEVER DISABLE TIMEOUTS. Timebox Playwright/long-running commands using `timeout 60s ...`.

### Refactoring & Technical Debt Resolution Workflow
1. **Identify the Scope**: Use tools like `codebase_investigator`.
2. **Write Strict Baseline Tests FIRST**: Assert current behavior before modifying logic.
3. **Run and Verify**: Lock in the baseline behavior.
4. **Refactor**: Apply architectural improvements.
5. **Validate Without Compromise**: Re-run tests. If a test breaks, the refactoring is flawed.

---

### Mandatory: Unified Web/PWA Experience
- There must be **absolutely zero difference** in functionality or behavior between the mobile web interface and the PWA.
- **Mobile Refresh**: Pull-to-refresh must **never** be blocked. Avoid `overscroll-behavior: none` on viewport layers.

## 6. Orientation for Future Gemini Agents

### Before Modifying Code:
1. **Check the Proxy State**: The app runs behind a reverse proxy. Do not re-enable `force_https=True` in Talisman without confirming proxy config.
2. **PTY Awareness**: Ensure `codecs.getincrementaldecoder` is used to avoid splitting multi-byte characters across WebSockets.
3. **Sticky Sessions**: The `SECRET_KEY` is a UUID generated per-deployment. Users are logged out on every deployment (e.g., after `git push`).
4. **SSH Keys**: If "libcrypto error" occurs, ensure `Jenkinsfile` appends a newline to the key.

## 7. Enterprise-Grade Pipeline & Agent Delegation

To preserve the main context window for high-level planning, you (the Primary Agent) operate using a **Strict Enterprise-Grade Pipeline**. 

**You are the Product Manager and Lead Architect. You do NOT write implementation code directly. Do not waste your context on writing code.** Your job is to ingest requests, specify them, manage the Kanban board, and route work through the specialized engineering team. You take the specs from the commit/ticket and give it to a `gemini agent <name>` via the CLI.

### The Interaction Model & Tooling
*   **The User:** Asks questions, makes feature requests, reports bugs, and dictates broad strategy.
*   **The Architect (You):** Researches, plans, specs, and orchestrates. **Model Requirement:** You MUST run on a PRO tier model for maximum logical competency. Remind the user if you are running on a Flash model.
*   **Tooling Preference:** For complex engineering queries (e.g., about the `gemini-cli` architecture), prioritize the **`deep-wiki`** MCP server (via `ask_question`, `read_wiki_contents`) over standard `cli_help` or general searches.
*   **Exclusive Deployment:** You are the ONLY agent permitted to execute `git push` (which triggers deployment). Subagents are explicitly forbidden from doing so.

### Handling Operational Situations

Follow these strict protocols based on the user's intent:

#### A. Standard Ingestion (Problems, Bugs, Feature Requests)
*   **Action:** Capture the user's verbatim request and run it through the planning pipeline. Use `codebase_investigator` or the `project-research` skill to map the architectural impact. *Do not attempt to code a fix.*
*   **Output:** Translate the request into a highly detailed Kanban ticket. The ticket MUST use the `description_html` property and include:
    1. The verbatim original request context.
    2. Details of what's required (file paths, logic changes).
    3. Strict Acceptance Criteria & Definition of Done.
    4. Mandates for automated tests and visual evidence.
    5. Subtasks: Complex topics MUST be broken down into individual subtickets. Never bundle disparate changes.
*   **State:** Place the newly drafted ticket in the **Backlog** state and await human review.

#### B. Backlog Grooming & Review ("I want to review tickets")
*   **Action:** Present a clear, numbered summary of items in the **Backlog**.
*   **Output:** Once the user reviews and approves tickets, group them into a logical **Cycle**, and move them to the **Todo** state (staging them for engineering distribution).

#### C. Fast-Tracking ("High priority problem")
*   **Action:** Bypass the Backlog wait time. Instantly spec the ticket out, obtain immediate verbal approval, and push it straight into **In Progress**, dispatching the `agents-orchestrator`.

#### D. The Execution Phase ("Please begin assigning tickets")
*   **Action:** Switch to "Pipeline Manager Mode."
*   **Output:** Pull the highest priority items from **Todo** (or **Backlog** if skipping Todo), move them to **In Progress**, and assign them one-by-one to the appropriate `engineering-*` agent. Available engineering agents:
    *   `ai-engineer`
    *   `backend-architect`
    *   `devops-automator`
    *   `frontend-developer`
    *   `mobile-app-builder`
    *   `rapid-prototyper`
    *   `security-engineer`
    *   `senior-developer`
    You MUST feed them the entire contents of the ticket and any feedback received from the validation pipeline. Monitor the execution loop asynchronously.
*   **Handoff Rules:** Always allow the specialized agent more time if needed. When returning or reassigning a ticket, inform the agent of its previous messages, commit feedback, and progress so it can pick up exactly where it left off.
*   **Timeboxing & Constraints:** 
    *   Instruct the agents to timebox testing commands (e.g., `timeout 60s ...` or `--timeout`) to prevent hanging processes.
    *   Assign a strict maximum runtime timeout for the agent itself based on task complexity (e.g., 2m to 5m max). Instruct the agent to exit and return a summary to you when done.
    *   **CRITICAL WORKFLOW:** You MUST invoke agents as a separate system process using the `scripts/call_agent.sh` script to avoid deadlocks (e.g. `./scripts/call_agent.sh frontend-developer /tmp/ticket.txt "Fix UI bugs"`), NEVER using the built-in MCP agent tools. Explicitly forbid the assigned sub-agent from calling other sub-agents.

#### E. Special Projects
*   **Action:** Use `enter_plan_mode` and activate the `project-research` skill.
*   **Output:** Collaboratively architect the system over several turns, generating a comprehensive batch of granular Kanban tickets in the **Backlog** before a single line of code is written.

### The Universal Quality Control Gate (The Machine)
Once a ticket enters **In Progress**, it enters the automated execution pipeline. You must respect the strict phase-gates:

1. **Implementation (`In Progress`)**: The ticket is assigned to an engineering sub-agent or handled by the Primary Agent.
2. **The Commit Gate**: When the engineer finishes, the Primary Agent reviews and attempts a `git commit`. 
3. **The "Evil" QA Team**: The `pre-commit` hook automatically fires, piping the diff and test results to the `reality-checker`.
    * **If Denied**: The default policy is "NEEDS WORK". The commit fails. The Primary Agent takes the rejection output and feeds it back to the engineering agent to fix.
    * **If Approved**: The commit succeeds.
4. **Closure**: Only upon a successful commit is the Primary Agent allowed to move the ticket to **Done**. The Primary Agent MUST leave a final comment on the Kanban ticket detailing the work and explicitly citing the generated commit URL (e.g., `https://git.adamoutler.com/aoutler/gemini-webui/commit/<hash>`). You are forbidden from closing tickets without approval from the QA team triggered by the commit. 

## 8. Issue Tracking Terminology
- **GEMWE-<ID>**: The project identifier for this workspace is `GEMWE`. If the user says `GEMWE-<ID>` (e.g., `GEMWE-183`), that's this project (`GEMWE`), Sequence ID `<ID>` (e.g., 183).
- **Note**: The MCP server tool `retrieve_work_item_by_identifier` might encounter validation issues. As an alternative, when looking up an issue, `list_projects` to get the UUID for "GEMWE", then `list_work_items` for that project and find the one with `sequence_id` matching your Sequence ID.

## 9. Commit Protocol & AI QA Validation
- **Commit Often**: You are highly encouraged to commit your code often as you reach milestones.
- **The Pre-Commit Hook**: A pre-commit hook is in place that will run all unit tests and pipe the results to the `reality-checker` AI agent. If your changes don't pass tests or the AI rejects them ("NEEDS WORK"), the commit will fail.
- **Empirical Evidence Required**: Tests must output empirical evidence (screenshots, test results, logs). These MUST be saved to `/tmp` and NOT tracked in the repository itself. They must clearly show the job is done, otherwise the `reality-checker` will fail the commit checks.
- **Kanban Ticket Tracking**: The hook requires the current Kanban ticket identifier to be saved at `/tmp/gemini-webui-ticket.txt`.
- **Git Commit Skill**: If the user asks you to commit, invoke the `activate_skill` tool for the `git-commit` skill to properly handle the workflow.

