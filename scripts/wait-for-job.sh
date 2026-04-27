#!/bin/bash
# wait-for-job.sh
# Queues a job in Gemini WebUI Automation Bridge and polls until completion.

set -e

# Defaults
GEMWEBUI_URL="${GEMWEBUI_URL:-http://localhost:5001}"
POLL_INTERVAL=5
MODE="strict"
TIMEOUT=300

usage() {
    echo "Usage: $0 --tab <tab_id> --prompt <command> [--mode strict|heuristic] [--timeout seconds]"
    exit 1
}

while [[ "$#" -gt 0 ]]; do
    case $1 in
        --tab) TAB_ID="$2"; shift ;;
        --prompt) PROMPT="$2"; shift ;;
        --mode) MODE="$2"; shift ;;
        --timeout) TIMEOUT="$2"; shift ;;
        *) usage ;;
    esac
    shift
done

if [[ -z "$TAB_ID" || -z "$PROMPT" ]]; then
    usage
fi

if [[ -z "$GEMINI_API_KEY" ]]; then
    echo "Error: GEMINI_API_KEY environment variable is required."
    exit 1
fi

echo "Queueing job on tab '$TAB_ID': $PROMPT"

QUEUE_RESP=$(curl -s -X POST "$GEMWEBUI_URL/api/v1/automation/queue" \
    -H "Authorization: Bearer $GEMINI_API_KEY" \
    -H "Content-Type: application/json" \
    -d "{\"tab_id\": \"$TAB_ID\", \"prompt\": \"$PROMPT\", \"mode\": \"$MODE\", \"timeout\": $TIMEOUT}")

JOB_ID=$(echo "$QUEUE_RESP" | grep -o '"job_id": *"[^"]*"' | cut -d'"' -f4)

if [[ -z "$JOB_ID" ]]; then
    echo "Failed to queue job. Response: $QUEUE_RESP"
    exit 1
fi

echo "Job queued with ID: $JOB_ID. Waiting for completion..."

while true; do
    STATUS_RESP=$(curl -s -X GET "$GEMWEBUI_URL/api/v1/automation/jobs/$JOB_ID" \
        -H "Authorization: Bearer $GEMINI_API_KEY")

    STATUS=$(echo "$STATUS_RESP" | grep -o '"status": *"[^"]*"' | cut -d'"' -f4)

    if [[ "$STATUS" == "completed" ]]; then
        echo "Job completed successfully."
        EXIT_CODE=$(echo "$STATUS_RESP" | grep -o '"exit_code": *[0-9]*' | cut -d':' -f2 | tr -d ' ' | tr -d '}')
        echo "--- OUTPUT ---"
        echo "$STATUS_RESP"
        echo "--------------"
        echo "Exit code: $EXIT_CODE"
        exit "${EXIT_CODE:-0}"
    elif [[ "$STATUS" == "failed" ]]; then
        echo "Job failed."
        echo "$STATUS_RESP"
        exit 1
    elif [[ "$STATUS" == "queued" || "$STATUS" == "running" ]]; then
        sleep "$POLL_INTERVAL"
    else
        echo "Unknown status: $STATUS. Response: $STATUS_RESP"
        exit 1
    fi
done
