#!/bin/bash
PROJECT=gemwebui
PAYLOAD=$(cat -)
STATE=$(echo "$PAYLOAD" | jq -r '.tool_input.state // empty')
PROJECT_ID=$(echo "$PAYLOAD" | jq -r '.tool_input.project_id // empty')
WORK_ITEM_ID=$(echo "$PAYLOAD" | jq -r '.tool_input.work_item_id // empty')

if [[ -z "$STATE" || -z "$PROJECT_ID" || -z "$WORK_ITEM_ID" ]]; then
    echo '{"decision": "allow"}'
    exit 0
fi

# Rate limit check: Ensure at least 30s between calls
CURRENT_TIME=$(date +%s)
if [ -f /tmp/qa_gate_last_run ]; then
    LAST_RUN=$(cat /tmp/qa_gate_last_run)
    DIFF=$((CURRENT_TIME - LAST_RUN))
    if [ "$DIFF" -lt 30 ]; then
        jq -c -n --arg reason "Rate limit exceeded. Please wait 30 seconds between calls to mcp update ticket." '{"decision": "deny", "reason": $reason}'
        exit 0
    fi
fi
echo "$CURRENT_TIME" > /tmp/qa_gate_last_run

# Look up the state dynamically to avoid hardcoding the UUID
DONE_STATE_ID=$(curl -s -X GET "https://kanban.hackedyour.info/api/v1/workspaces/${PROJECT}/projects/$PROJECT_ID/states/" \
  -H "x-api-key: $KANBAN_API_KEY" \
  -H "Content-Type: application/json" | jq -r '.results[] | select(.name == "Done") | .id')

if [[ "$STATE" == "$DONE_STATE_ID" ]]; then

  # Pre-flight QA checks
  if [[ -n $(git status --porcelain) ]]; then
    jq -c -n --arg reason "please commit all project files and delete non-project files - if there are any uncommitted files." '{"decision": "deny", "reason": $reason}'
    exit 0
  fi

  if git status -sb | grep -q 'ahead'; then
    jq -c -n --arg reason "Git repository has unpushed commits. Please push changes before QA to ensure we match the main repo." '{"decision": "deny", "reason": $reason}'
    exit 0
  fi

  # Check Jenkins build status before invoking AI
  if ! grep -q "Gemini WebUI Build Finished: SUCCESS" /tmp/jenkins-receipt-gemini-webui.log 2>/dev/null; then
    jq -c -n --arg reason "Jenkins build failed or receipt not found. Please resolve build issues before transitioning to Done." '{"decision": "deny", "reason": $reason}'
    exit 0
  fi

  # Retrieve the ticket
  TICKET_JSON=$(curl -s -X GET "https://kanban.hackedyour.info/api/v1/workspaces/${PROJECT}/projects/$PROJECT_ID/issues/$WORK_ITEM_ID/" \
    -H "x-api-key: $KANBAN_API_KEY" \
    -H "Content-Type: application/json")

  # Retrieve the ticket comments and format them to reduce context size
  TICKET_COMMENTS=$(curl -s -X GET "https://kanban.hackedyour.info/api/v1/workspaces/${PROJECT}/projects/$PROJECT_ID/issues/$WORK_ITEM_ID/comments/" \
    -H "x-api-key: $KANBAN_API_KEY" \
    -H "Content-Type: application/json" | jq -r '
      .results[] | "User Id: \(.created_by)\nLast Updated: \(.updated_at // .created_at)\n\(.comment_html)\nAttachments: \(.attachments | tojson)\n---"
    ')

  TICKET_NAME=$(echo "$TICKET_JSON" | jq -r '.name // "Unknown Ticket"')
  TICKET_FILE="/tmp/ticket_${WORK_ITEM_ID}.md"

  cat <<EOF > "$TICKET_FILE"
---
name: $TICKET_NAME
description: The kanban ticket to be closed. This should be evaluated as the reference source for ticket completion and the criteria for evaluation.
---
$TICKET_JSON

---
name: Kanban Ticket Comments
description: The discussion and history on the ticket including any attachments.
---
${TICKET_COMMENTS}

---
name: Jenkins Build Receipt
description: the build results from jenkins
---
$(cat /tmp/jenkins-receipt-gemini-webui.log 2>/dev/null)
EOF

  RESULT=$(cat "$TICKET_FILE" | gemini -p "@reality-checker Please verify if work item $WORK_ITEM_ID is completed. You don't get the work items from the filesystem. Use the list_files and read_file tool to find proof. You may request any additional information you need in a specific location. Be descriptive. Otherwise, respond with NEEDS WORK." 2>&1)
  GEMINI_EXIT_CODE=$?

  if [ $GEMINI_EXIT_CODE -ne 0 ]; then
    jq -c -n --arg reason "No quality control available. Gemini command exited with $GEMINI_EXIT_CODE. Output: $RESULT" '{"decision": "deny", "reason": $reason}'
    exit 0
  fi

  COMMENT_PAYLOAD=$(jq -n --arg html "$RESULT" '{"comment_html": $html}')
  curl -s -X POST "https://kanban.hackedyour.info/api/v1/workspaces/${PROJECT}/projects/$PROJECT_ID/issues/$WORK_ITEM_ID/comments/" \
    -H "x-api-key: $KANBAN_API_KEY" \
    -H "Content-Type: application/json" \
    -d "$COMMENT_PAYLOAD" > /dev/null

  if ! grep -q "NEEDS WORK" <<< "$RESULT"; then
    echo '{"decision": "allow"}'
    exit 0
  else
    jq -c -n --arg reason "Reality checker blocked the transition to Done. Please review the ticket comments for details." '{"decision": "deny", "reason": $reason}'
    exit 0
  fi
fi

echo '{"decision": "allow"}'
