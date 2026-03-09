---
name: ticket-audit
description: Skill for auditing closed Kanban tickets to ensure they comply with the strict commit URL annotation policy. Use this when the user asks to run an audit or check ticket compliance.
---

# Kanban Ticket Audit Workflow

The project mandates a strict engineering pipeline rule: Any ticket with a sequence ID >= 137 MUST contain a valid Git commit URL in its comments before being closed/moved to the Done state.

When asked to audit tickets, follow these steps:

1. **Execute the Audit Script**:
   Run the dedicated Python script that interfaces with the Kanban API:
   ```bash
   python3 scripts/audit_tickets.py
   ```

2. **Analyze the Results**:
   * If the script reports `--- AUDIT PASSED ---`, inform the user that all completed tickets meet the compliance standards.
   * If the script reports `--- AUDIT FAILED ---`, it will list the specific `GEMWE-<ID>` tickets that are violating the policy.

3. **Take Corrective Action**:
   For any ticket that fails the audit, you MUST recommend one of two paths to the user:
   * **Re-open the ticket**: Use the `update_work_item` MCP tool to move the ticket back to the `In Progress` state (State ID: `d142bbba-7042-4eab-88bc-88dea4f60ba9`).
   * **Backfill the URL**: If you have the commit hash from the git history, construct the URL (`https://git.adamoutler.com/aoutler/gemini-webui/commit/<hash>`) and use the `create_work_item_comment` MCP tool to add it to the ticket.

Do not manually transition any violating ticket to the "Done" state unless the audit passes or you explicitly injected the required URL.