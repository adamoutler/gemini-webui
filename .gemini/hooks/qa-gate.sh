#!/bin/bash
# =============================================================================
# QA Gate Bypass Flags (FOR TESTING ONLY)
# =============================================================================
BYPASS_UNCOMMITTED=false # If true, allows closing tickets even with uncommitted changes.
BYPASS_PUSHED=false      # If true, allows closing tickets even if local branch is ahead of origin.
BYPASS_CI=false          # If true, skips the GitHub Actions build status verification.
# =============================================================================

SERVER="https://kanban.hackedyour.info"
PROJECT=gemwebui

if [[ -z "${KANBAN_API_KEY:-}" ]]; then
    jq -c -n --arg reason "GATE DENIED: KANBAN_API_KEY is not set in the environment." '{"decision": "deny", "reason": $reason}'
    exit 0
fi

PAYLOAD=$(cat -)
STATE=$(echo "$PAYLOAD" | jq -r '.tool_input.state // .tool_input.state_name // empty')
WORK_ITEM_ID=$(echo "$PAYLOAD" | jq -r '.tool_input.work_item_id // empty')
TICKET_ID=$(echo "$PAYLOAD" | jq -r '.tool_input.ticket_id // empty')
TOOL_NAME=$(echo "$PAYLOAD" | jq -r '.tool_name')

if [[ -z "$TICKET_ID" ]]; then
    echo '{"decision": "allow"}'
    exit 0
fi

PREFIX="${TICKET_ID%%-*}"
NUMBER="${TICKET_ID##*-}"

if [[ -z "$PREFIX" || -z "$NUMBER" || "$PREFIX" == "$NUMBER" ]]; then
    jq -c -n --arg reason "GATE DENIED: Invalid ticket ID format. Expected PREFIX-NUMBER (e.g., GEMWEBUI-123)" '{"decision": "deny", "reason": $reason}'
    exit 0
fi

# Validate NUMBER is numeric
if ! [[ "$NUMBER" =~ ^[0-9]+$ ]]; then
    jq -c -n --arg reason "GATE DENIED: Invalid ticket number '$NUMBER'. Must be numeric." '{"decision": "deny", "reason": $reason}'
    exit 0
fi

PROJECT_ID=$(curl -s --max-time 30 -X GET "${SERVER}/api/v1/workspaces/${PROJECT}/projects/" \
    -H "x-api-key: $KANBAN_API_KEY" \
    -H "Content-Type: application/json" \
    | jq -r ".results[] | select(.identifier == \"$PREFIX\") | .id")

if [[ -z "$PROJECT_ID" || "$PROJECT_ID" == "null" ]]; then
    jq -c -n --arg reason "GATE DENIED: Could not find project with identifier '$PREFIX'" '{"decision": "deny", "reason": $reason}'
    exit 0
fi

if [[ -z "$WORK_ITEM_ID" ]]; then
    TICKET_INFO=$(curl -s -X GET "${SERVER}/api/v1/workspaces/${PROJECT}/projects/${PROJECT_ID}/issues/?search=$TICKET_ID" \
      -H "x-api-key: $KANBAN_API_KEY")
    SEQ=$(echo "$TICKET_ID" | cut -d'-' -f2)
    WORK_ITEM_ID=$(echo "$TICKET_INFO" | jq -r ".results[] | select(.sequence_id == $SEQ) | .id")
fi

if [[ -z "$WORK_ITEM_ID" || "$WORK_ITEM_ID" == "null" ]]; then
    jq -c -n --arg reason "GATE DENIED: Could not find issue ${TICKET_ID} in project ${PREFIX}" '{"decision": "deny", "reason": $reason}'
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
DONE_STATE_ID=$(curl -s -X GET "${SERVER}/api/v1/workspaces/${PROJECT}/projects/$PROJECT_ID/states/" \
  -H "x-api-key: $KANBAN_API_KEY" \
  -H "Content-Type: application/json" | jq -r '.results[] | select(.name == "Done") | .id')

if [[ "$STATE" == "$DONE_STATE_ID" || "$STATE" == "Done" || "$TOOL_NAME" == *"complete_work"* ]]; then

  # Pre-flight QA checks
  
  # 1. Uncommitted Changes Check
  if [[ "$BYPASS_UNCOMMITTED" != "true" ]]; then
    if [[ -n $(git status --porcelain) ]]; then
      jq -c -n --arg reason "please commit all project files and delete non-project files - if there are any uncommitted files." '{"decision": "deny", "reason": $reason}'
      exit 0
    fi
  fi

  # 2. Unpushed Commits Check
  if [[ "$BYPASS_PUSHED" != "true" ]]; then
    if git status -sb | grep -q 'ahead'; then
      jq -c -n --arg reason "Git repository has unpushed commits. Please push changes before QA to ensure we match the main repo." '{"decision": "deny", "reason": $reason}'
      exit 0
    fi
  fi

  # 3. CI/CD Success Check
  if [[ "$BYPASS_CI" != "true" ]]; then
    CURRENT_COMMIT=$(git rev-parse HEAD)
    RUN_JSON=$(gh run list --commit "$CURRENT_COMMIT" --json databaseId,conclusion -q '.[0]')
    RUN_ID=$(echo "$RUN_JSON" | jq -r '.databaseId // empty')
    CONCLUSION=$(echo "$RUN_JSON" | jq -r '.conclusion // empty')

    if [[ -z "$RUN_ID" || "$RUN_ID" == "null" ]]; then
      jq -c -n --arg reason "No GitHub Actions run found for the current commit $CURRENT_COMMIT. Please push your changes and wait for checks to pass." '{"decision": "deny", "reason": $reason}'
      exit 0
    fi

    if [[ "$CONCLUSION" != "success" ]]; then
      jq -c -n --arg reason "GitHub Actions run $RUN_ID did not succeed (status: $CONCLUSION). Please fix the build before transitioning to Done." '{"decision": "deny", "reason": $reason}'
      exit 0
    fi
  fi
  
  CURRENT_COMMIT=$(git rev-parse HEAD)
  RUN_JSON=$(gh run list --commit "$CURRENT_COMMIT" --json databaseId,conclusion -q '.[0]')
  RUN_ID=$(echo "$RUN_JSON" | jq -r '.databaseId // empty')
  GH_RUN_VIEW=$(gh run view "$RUN_ID" 2>/dev/null || echo "No build details available (CI check bypassed or run missing).")

  # Retrieve the ticket
  TICKET_JSON=$(curl -s -X GET "${SERVER}/api/v1/workspaces/${PROJECT}/projects/$PROJECT_ID/issues/$WORK_ITEM_ID/" \
    -H "x-api-key: $KANBAN_API_KEY" \
    -H "Content-Type: application/json")

  # Retrieve the ticket comments and format them to reduce context size
  TICKET_COMMENTS=$(curl -s -X GET "${SERVER}/api/v1/workspaces/${PROJECT}/projects/$PROJECT_ID/issues/$WORK_ITEM_ID/comments/" \
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
name: GitHub Actions Build Receipt
description: The build results from GitHub Actions for commit $CURRENT_COMMIT
---
$GH_RUN_VIEW
EOF

  echo "allowing time to settle before reality checker" >&2
  sleep 20

  PROMPT="You are invoked as clean-room ticket-completeness evaluation agent. Please relay the provided context to subagent @reality-checker and provde the complete response. The expectation is reality-checker will provide NEEDS WORK if not ready or READY if ready. The system is monitoring for keyword 'NEEDS WORK'. The full response will be recorded on the kanban ticket and relayed to the agent as feedback."

  OUTPUT_FILE=$(mktemp)
  cat "$TICKET_FILE" | gemini -y -p "$PROMPT" --output-format=json > "$OUTPUT_FILE" 2>/dev/null
  GEMINI_EXIT_CODE=$?

  if [ $GEMINI_EXIT_CODE -ne 0 ]; then
    jq -c -n --arg reason "No quality control available. Gemini command exited with $GEMINI_EXIT_CODE. Find the full transaction at $OUTPUT_FILE for troubleshooting purposes." '{"decision": "deny", "reason": $reason}'
    exit 0
  fi

  RESULT=$(jq -r '.response // empty' "$OUTPUT_FILE")

  if [[ ${#RESULT} -lt 200 ]]; then
    jq -c -n --arg res "$RESULT" --arg reason "Reality Checker response too short (${#RESULT} chars). Expected verbose report (>200 chars). Find the full transaction at $OUTPUT_FILE for troubleshooting purposes." '{"decision": "deny", "reason": $reason}'
    exit 0
  fi

  COMMENT_PAYLOAD=$(jq -n --arg html "$RESULT" '{"comment_html": $html}')
  curl -s -X POST "${SERVER}/api/v1/workspaces/${PROJECT}/projects/$PROJECT_ID/issues/$WORK_ITEM_ID/comments/" \
    -H "x-api-key: $KANBAN_API_KEY" \
    -H "Content-Type: application/json" \
    -d "$COMMENT_PAYLOAD" > /dev/null

  if grep -q "READY" <<< "$RESULT"; then
    echo '{"decision": "allow"}'
    exit 0
  else
    jq -c -n --arg reason "Reality Checker determined the work is not ready. Feedback: $RESULT" '{"decision": "deny", "reason": $reason}'
    exit 0
  fi
fi

echo '{"decision": "allow"}'
