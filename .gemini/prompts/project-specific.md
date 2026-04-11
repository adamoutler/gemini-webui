## 🏗️ Gemini WebUI Technical Addendum

### 1. Architectural Mandates
* **Connectivity:** Support both **Local PTY** (inside container) and **SSH Tunnels** (to target hosts).
* **PTY Integrity:** Use `codecs.getincrementaldecoder` for UTF-8 streaming to prevent multi-byte character mangling in `xterm.js`.
* **Persistence:** Maintain state via `/home/node/.gemini` (mounted host `~/.gemini`).
* **Mobile/PWA:** Zero functional difference between Web and PWA. Never block pull-to-refresh (`overscroll-behavior: none` is forbidden on viewport layers).

---

### 2. The Universal Quality Control Gate ("The Machine")
* **Commit Gate:** Every commit is intercepted by an automated QA agent.
* **Ticket Tracking:** The current **Kanban ID** must be written to `/tmp/gemini-webui-ticket.txt` before any git commit attempt.
* **Empirical Evidence:** QA requires visual proof (screenshots) or logs saved to `/tmp`. These must **NOT** be tracked in the repo.
* **Rejection Policy:** Default to **"NEEDS WORK"**. If a commit fails, feed the rejection reason back to the developer agent immediately.

---

### 3. Deployment & Recovery Protocol (Zero-Downtime)
* **The Push Rule:** `git push` is blocked. You MUST use `git p` as it is the only way.
* **Pre-Push Warning:** You must state: *"Executing git p. I will lose context. When you resume, I will check the build receipt."*
* **Post-Resume Recovery:**
    1. Read `/tmp/jenkins-receipt-gemini-webui.log` to verify build success.
    2. Run `git status` to re-orient.
    3. Check `/tmp/gemini-webui-ticket.txt` to resume the active task.

---

### 4. Testing & Refactoring Standards
* **Baseline First:** For refactors, write strict baseline tests asserting current behavior before modifying logic.
* **10-Second Rule:** Individual tests must never take longer than 10 seconds.
* **Timeout Safety:** Never disable timeouts; use `timeout 60s` for long-running Playwright/CLI commands.
* **Feedback Loop:** Every request requires a realtime feedback loop and corresponding unit test.

---

### 5. Tooling & Intelligence
* **Deep Research:** Prioritize the `deep-wiki` MCP server over standard searches for `gemini-cli` architecture.
* **Kanban Flow:**
    * **Backlog:** Verbatim user requests + detailed Acceptance Criteria.
    * **Todo:** Reviewed and approved cycles.
    * **In Progress:** Active execution with automated QA intercept.

