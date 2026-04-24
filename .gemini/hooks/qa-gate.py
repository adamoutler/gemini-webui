#!/usr/bin/env python3
"""
QA Gate Evaluation Script
Validates criteria before allowing a Kanban ticket to transition to Done.

echo '{"tool_name": "mcp_kanban_complete_work", "tool_input": {"ticket_id": "SSH-91"}}' |  python3 qa-gate.py
echo '{"tool_name": "mcp_foobarbazbuzz_transition_ticket", "tool_input": {"ticket_id": "SSH-91", "state_name": "done"}}' |  python3 qa-gate.py
"""

import os
import sys
import json
import time
import fcntl
import subprocess
import urllib.request
import urllib.parse

# =============================================================================
# 0. Static Variables & Configuration
# =============================================================================
SERVER = "https://kanban.hackedyour.info"
WORKSPACE = "gemwebui"  # Kanban workspace identifier (URL segment)
# Format: provider/owner/repo/workflow_name
DASH = "github/adamoutler/gemini-webui/Build and Publish"

# QA Gate Bypass Flags (FOR TESTING ONLY)
BYPASS_UNCOMMITTED = False
BYPASS_REALITY = False
BYPASS_PUSHED = False
BYPASS_CI = False

# =============================================================================
# Core Utility Functions
# =============================================================================

def allow_transition():
    """Outputs an allow decision to MCP and terminates execution."""
    print(json.dumps({"decision": "allow"}))
    sys.exit(0)

def deny_transition(reason):
    """Outputs a deny decision with the specified reason to MCP and terminates."""
    print(json.dumps({"decision": "deny", "reason": reason}))
    sys.exit(0)

def api_request(endpoint, method="GET", data=None):
    """Executes an authenticated HTTP request against the Kanban API."""
    url = f"{SERVER}{endpoint}"
    headers = {"x-api-key": os.environ.get("KANBAN_API_KEY", ""), "Content-Type": "application/json"}
    req_data = json.dumps(data).encode() if data else None
    req = urllib.request.Request(url, data=req_data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=30) as res:
            if res.status == 204:
                return None
            return json.loads(res.read().decode())
    except Exception:
        return None

def dash_api_request(url):
    """Executes a GET request against the Dash API."""
    req = urllib.request.Request(url, headers={'accept': 'application/json'})
    try:
        with urllib.request.urlopen(req, timeout=30) as res:
            return json.loads(res.read().decode())
    except Exception as e:
        return None

def acquire_lock():
    """Implements a non-blocking POSIX file lock to prevent concurrent QA evaluations."""
    f = open("/tmp/qa-gate.lock", 'a+')
    try:
        fcntl.flock(f, fcntl.LOCK_EX | fcntl.LOCK_NB)
        f.seek(0)
        f.truncate()
        f.write(str(int(time.time())))
        f.flush()
        return f
    except BlockingIOError:
        try:
            f.seek(0)
            lock_time = int(f.read().strip())
            try_again = time.strftime("%H:%M:%S", time.localtime(lock_time + 300))
        except Exception:
            try_again = "in 5 minutes"
        deny_transition(f"Another QA assessment is currently in progress. Please try again at {try_again}.")

# =============================================================================
# Validation Functions (Steps 3-7)
# =============================================================================

def verify_kanban_key():
    """3. Ensures the required API token is present in the environment."""
    if "KANBAN_API_KEY" not in os.environ:
        deny_transition("GATE DENIED: KANBAN_API_KEY is not set in the environment.")

def verify_git_clean():
    """4. Validates the local git working tree has no uncommitted changes."""
    if BYPASS_UNCOMMITTED: return
    status = subprocess.run(["git", "status", "--porcelain"], capture_output=True, text=True).stdout.strip()
    if status:
        deny_transition("Please commit all project files and delete non-project files - if there are any uncommitted files.")

def verify_git_pushed():
    """5. Validates that the local branch is not ahead of its remote tracking counterpart."""
    if BYPASS_PUSHED: return
    status = subprocess.run(["git", "status", "-sb"], capture_output=True, text=True).stdout
    if not status or "..." not in status.splitlines()[0]:
        deny_transition("Git branch has no upstream tracking branch. Please push changes before QA to ensure we match the main repo.")
    if "ahead" in status:
        deny_transition("Git repository has unpushed commits. Please push changes before QA to ensure we match the main repo.")

def verify_dash_ci():
    """6. Queries the Dash API for the build status matching the DASH environment string."""
    if BYPASS_CI: return None

    if not DASH:
        deny_transition("GATE DENIED: DASH configuration variable is not set (e.g., github/adamoutler/repo/Workflow).")

    parts = DASH.split('/', 3)
    if len(parts) < 4:
        deny_transition(f"GATE DENIED: Invalid DASH format '{DASH}'. Expected provider/owner/repo/workflow_name.")

    provider, owner, repo, workflow_name = parts[0], parts[1], parts[2], parts[3]

    status_data = dash_api_request("https://dash.hackedyour.info/api/status")
    if not status_data:
        deny_transition("GATE DENIED: Could not fetch CI status from Dash API.")

    target_job = None
    for job in status_data:
        if (job.get("provider") == provider and
            job.get("owner") == owner and
            job.get("repo") == repo and
            job.get("workflow_name") == workflow_name):
            target_job = job
            break

    if not target_job:
        deny_transition(f"GATE DENIED: No CI job found matching '{DASH}' in Dash.")

    if target_job.get("status") != "success":
        deny_transition(f"CI job '{DASH}' did not succeed (status: {target_job.get('status')}). Please fix the build.")

    return target_job

# =============================================================================
# Kanban API Helpers (Step 7)
# =============================================================================

def fetch_project_id(workspace, prefix):
    data = api_request(f"/api/v1/workspaces/{workspace}/projects/")
    if not data: return None
    for p in data.get("results", []):
        if p.get("identifier") == prefix:
            return str(p.get("id"))
    return None

def fetch_work_item(workspace, project_id, ticket_id, seq):
    data = api_request(f"/api/v1/workspaces/{workspace}/projects/{project_id}/issues/?search={ticket_id}")
    if not data: return None
    for w in data.get("results", []):
        if str(w.get("sequence_id")) == str(seq):
            return str(w.get("id"))
    return None

def fetch_done_state(workspace, project_id):
    data = api_request(f"/api/v1/workspaces/{workspace}/projects/{project_id}/states/")
    if not data: return None
    for s in data.get("results", []):
        if s.get("name", "").lower() == "done":
            return str(s.get("id"))
    return None

def build_ticket_context(workspace, project_id, work_item_id, commit, ci_job):
    """7. Prepares payload for AI QA gate using the dash apis."""
    ticket = api_request(f"/api/v1/workspaces/{workspace}/projects/{project_id}/issues/{work_item_id}/")
    comments = api_request(f"/api/v1/workspaces/{workspace}/projects/{project_id}/issues/{work_item_id}/comments/")

    name = ticket.get("name", "Unknown Ticket") if ticket else "Unknown Ticket"
    md = f"---\nname: {name}\ndescription: The kanban ticket to be closed. Reference source for ticket completion.\n---\n{json.dumps(ticket, indent=2)}\n\n"
    md += "---\nname: Kanban Ticket Comments\ndescription: Discussion and history on the ticket including attachments.\n---\n"

    if comments:
        for c in comments.get("results", []):
            md += f"User Id: {c.get('created_by')}\nLast Updated: {c.get('updated_at') or c.get('created_at')}\n{c.get('comment_html')}\nAttachments: {json.dumps(c.get('attachments'))}\n---\n"

    if ci_job and ci_job.get("workflow_id"):
        query = urllib.parse.urlencode({
            'provider': ci_job.get('provider'),
            'owner': ci_job.get('owner'),
            'repo': ci_job.get('repo'),
            'workflow_id': ci_job.get('workflow_id')
        })
        log_url = f"https://dash.hackedyour.info/api/logs?{query}"
        log_data = dash_api_request(log_url)

        if log_data and "log" in log_data:
            full_log = log_data["log"]
            log_lines = full_log.splitlines()
            # Equivalent to tail -n 100 to reduce context window load
            dash_view = "\n".join(log_lines[-100:])
        else:
            dash_view = "No logs returned from Dash."
    else:
        dash_view = "No build details available (CI check bypassed or missing workflow_id)."

    md += f"---\nname: Dash Build Receipt\ndescription: The build results from Dash CI for commit {commit}\n---\n{dash_view}"

    return md

# =============================================================================
# Reality Checker Execution (Step 8)
# =============================================================================

def run_reality_checker(ticket_md):
    """8. Checks with reality-checker AI to verify it's done."""
    prompt = "You are invoked as clean-room ticket-completeness evaluation agent. Please relay the provided context to subagent reality-checker and provde the complete response. The expectation is reality-checker will provide NEEDS WORK if not ready or READY if ready. The system is monitoring for keyword 'NEEDS WORK'. The full response will be recorded on the kanban ticket and relayed to the agent as feedback."

    time.sleep(20)

    try:
        proc = subprocess.run(
            ["gemini", "-y", "-p", prompt, "--output-format=json"],
            input=ticket_md,
            text=True,
            capture_output=True,
            timeout=1080
        )
    except subprocess.TimeoutExpired:
        deny_transition("GATE DENIED: The Reality Checker AI took too long to respond (timeout exceeded).")
    except Exception as e:
        deny_transition(f"GATE DENIED: Failed to execute Reality Checker: {str(e)}")

    if proc.returncode != 0:
        deny_transition(f"No quality control available. Gemini command exited with {proc.returncode}. Stderr: {proc.stderr}")

    try:
        res_data = json.loads(proc.stdout)
        result = res_data.get("response", "")
    except json.JSONDecodeError:
        result = ""

    if len(result) < 200:
        deny_transition(f"Reality Checker response too short ({len(result)} chars). Expected verbose report (>200 chars). Stderr: {proc.stderr}")

    return result

def post_kanban_comment(workspace, project_id, work_item_id, html):
    api_request(f"/api/v1/workspaces/{workspace}/projects/{project_id}/issues/{work_item_id}/comments/", method="POST", data={"comment_html": html})

# =============================================================================
# Main Execution Flow
# =============================================================================

if __name__ == "__main__":
    # 1. Gather payload variables
    payload_str = sys.stdin.read()
    if not payload_str.strip():
        allow_transition()

    payload = json.loads(payload_str)
    tool_input = payload.get("tool_input", {})
    tool_name = payload.get("tool_name", "")

    # Extract state_name from transition_ticket payloads
    state = str(tool_input.get("state") or tool_input.get("state_name") or "").lower()

    ticket_id = tool_input.get("ticket_id")
    work_item_id = tool_input.get("work_item_id")

    # 3. Key in environment
    verify_kanban_key()

    if not ticket_id or "-" not in ticket_id:
        deny_transition("GATE DENIED: Missing or invalid ticket ID format. Expected PREFIX-NUMBER.")

    prefix, number = ticket_id.split("-", 1)
    if not number.isdigit() or prefix == number:
        deny_transition(f"GATE DENIED: Invalid ticket number '{number}'.")

    project_id = fetch_project_id(WORKSPACE, prefix)
    if not project_id:
        deny_transition(f"GATE DENIED: Could not find project '{prefix}' in workspace '{WORKSPACE}'")

    done_state_id = fetch_done_state(WORKSPACE, project_id)

    # 2. Substring matching for dynamic MCP names, validating against the Done state or the macro
    is_completing_work = "_complete_work" in tool_name
    is_transition_to_done = "_transition_ticket" in tool_name and (state == "done" or state == str(done_state_id))

    if not (is_completing_work or is_transition_to_done):
        allow_transition()

    if not work_item_id:
        work_item_id = fetch_work_item(WORKSPACE, project_id, ticket_id, number)
    if not work_item_id:
        deny_transition(f"GATE DENIED: Could not find issue {ticket_id} in project '{project_id}'")

    lock_file = acquire_lock()

    try:
        # 4. Git repo is in pristine state
        verify_git_clean()

        # 5. All commits have been pushed upstream
        verify_git_pushed()

        # 6. CI/CD results are showing passed via Dash
        ci_job = verify_dash_ci()

       # 7. Prepare payload for AI QA gate using the dash apis
        commit = subprocess.run(["git", "rev-parse", "HEAD"], capture_output=True, text=True).stdout.strip()
        ticket_md = build_ticket_context(WORKSPACE, project_id, work_item_id, commit, ci_job)

        # 8. Check with reality-checker AI to verify it's done
        if BYPASS_REALITY:
            result_text = "READY: Reality check bypassed for testing."
        else:
            result_text = run_reality_checker(ticket_md)
            post_kanban_comment(WORKSPACE, project_id, work_item_id, result_text)

        # Must contain literal 'READY' and not contain 'NEEDS_WORK' (or 'NEEDS WORK')
        is_ready = "READY" in result_text and "NEEDS_WORK" not in result_text and "NEEDS WORK" not in result_text

        if is_ready:
            allow_transition()
        else:
            deny_transition(f"Reality Checker determined the work is not ready. Feedback: {result_text}")
    finally:
        lock_file.close()