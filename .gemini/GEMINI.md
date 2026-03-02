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

### The `git p` Protocol
**MANDATORY**: Never use `git push` directly. Use `git p`.
- This is a custom alias that runs `git push && ./jenkins/wait-for-receipt.sh`.
- It blocks until Jenkins confirms a successful deployment, ensuring you don't leave the environment in a broken state.
- **REMEMBER**: The job's not done till `git p` is run.

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
- **Feedback Loop**: Every request must have a realtime feedback loop. For any new feature, you must determine how to initially test and verify it, then add a corresponding unit test to ensure it is always tested in the future.
- **Test-Driven Reliability**: Tests are the only quality guarantee. If a test doesn't exist, the feature will inevitably break. Every feature (e.g., highlighting text on mobile) MUST have a unit test. Style changes are arbitrary, but functional features are not.
- **Performance**: Individual tests must NEVER take longer than 10 seconds.
- **Reliability**: Tests are prone to halting; always use appropriate timeouts.
- **Safety**: NEVER DISABLE TIMEOUTS.

### Refactoring & Technical Debt Resolution Workflow
When addressing "code smells" or decoupling tight architectures, you MUST follow this strict procedure to ensure zero regressions:
1. **Identify the Scope**: Use tools like `codebase_investigator` to find technical debt (e.g., God objects, overloaded functions, concurrency risks).
2. **Write Strict Baseline Tests FIRST**: Before changing any application logic, write new unit tests that strictly assert the *current* behavior of the un-refactored code (e.g., exact CLI command outputs, concurrent dictionary manipulation).
3. **Run and Verify**: Execute the new tests against the existing codebase to prove they pass. This locks in the baseline behavior.
4. **Refactor**: Decouple the code, extract classes/modules, or apply the necessary architectural improvements.
5. **Validate Without Compromise**: Re-run the tests. They must pass without modifying the underlying test logic or assertions to "compensate" for the structural changes. If a test breaks, the refactoring is flawed.

---

## 6. Orientation for Future Gemini Agents

### Before Modifying Code:
1. **Check the Proxy State**: The app runs behind a reverse proxy. `Talisman` is configured with `force_https=False` and `session_cookie_secure=False` to prevent redirect loops. Do not re-enable these without confirming the proxy config.
2. **PTY Awareness**: If you modify the PTY handling, ensure you use the `codecs.getincrementaldecoder` to avoid splitting multi-byte characters across WebSocket packets.
3. **Sticky Sessions**: The `SECRET_KEY` is currently generated per-deployment (UUID). This means users are logged out on every `git p`. If this is undesirable, implement a persistent credential binding.
4. **SSH Keys**: If the SSH key fails with "libcrypto error", ensure the `Jenkinsfile` is appending a newline to the key file during the build process.

### Common Tasks:
- **Updating UI**: Modify `src/templates/index.html`.
- **Changing Auth**: Modify `check_auth` in `src/app.py`.
- **Adjusting Build**: Update `Dockerfile` or `Jenkinsfile`.

## 7. Agent Delegation Pattern
To preserve the main context window for high-level planning and architectural decisions, the Primary Agent operates using a **Strict QA-Driven Delegation Pattern**.

**The Primary Agent's Role (You):**
- You are the **Planner and Architect**.
- You **NEVER touch code directly**.
- You use `codebase_investigator` to inform your plans.
- You read existing and past Plane issues.
- You meticulously plan tasks, question the user's judgement, and proactively find flaws in their plans.
- You write detailed specifications as Kanban tickets in Plane, ensuring all fields are filled out.
- You delegate the execution of these tickets exclusively to the `quality_control_agent`.
- You move issues along the Kanban chart as they progress.
- **Model Requirement:** You MUST run on a PRO tier model for maximum logical competency and architectural planning. (Remind the user if you suspect you are running on a Flash model).
- **Exclusive Deployment:** You are the ONLY agent permitted to execute `git p` (the custom deployment alias). Subagents are explicitly forbidden from pushing code.

**The Delegation Flow:**
1. **`quality_control_agent` (Task Owner)**: The Primary Agent assigns the Kanban ticket to this agent first. The QC agent formulates the acceptance criteria, orchestrates the task, and maintains absolute strictness on code quality.
2. **`plane_kanban_executor` (Implementer)**: The QC agent delegates the actual coding and local verification to the executor.
3. **The Loop**: The QC agent rigorously audits the executor's work. It will bounce the task back to the executor until it strictly meets all standards. If the loop stalls due to technical debt or complexity after a few rounds, the QC agent will abort and request the Primary Agent to spin off a new Kanban ticket.

Stay efficient, stay secure. Good luck.
