#!/bin/bash
# .gemini/hooks/qa-gate.sh

# Read JSON payload from stdin
PAYLOAD=$(cat -)

# Extract tool arguments using jq
STATUS=$(echo "$PAYLOAD" | jq -r '.tool_input.state // empty')
COMMENT=$(echo "$PAYLOAD" | jq -r '.tool_input.comment_html // empty')
TICKET_ID=$(echo "$PAYLOAD" | jq -r '.tool_input.work_item_id // empty')
PROJECT_ID=$(echo "$PAYLOAD" | jq -r '.tool_input.project_id // empty')

# Define the "Done" state ID (from Plane/Kanban configuration)
DONE_STATE_ID="ae56a905-81b7-4f9a-a2e5-7a842d66b8f4"

# Rule 1: Reject Orchestrator from directly closing tickets in mcp_kanban_update_work_item
if [[ "$STATUS" == "$DONE_STATE_ID" || "$STATUS" == "Done" ]]; then
  echo '{"decision": "deny", "reason": "SECURITY VIOLATION: AI Orchestrator cannot close tickets directly via update_work_item. You must add a comment with the commit hash via mcp_kanban_create_work_item_comment to trigger the reality-checker verification. Once verified, the CI/CD pipeline or hook will close the ticket."}'
  exit 0
fi

echo '{"decision": "allow"}'
