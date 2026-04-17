#!/usr/bin/bash
input=$(cat)
command=$(echo "$input" | jq -r '.tool_input.command // empty')
echo  "${input}">> /tmp/input.json

if [[ "$command" =~ (^|[[:space:]\;\&\|])git[[:space:]]+push([[:space:]]|$) ]]; then
    OWNER="adamoutler"
    REPO="gemini-webui"
    sleep 10

    # Use the wait endpoint to ensure we have waited for current build.
    curl -N -s "https://dash.hackedyour.info/api/wait?provider=github&owner=${OWNER}&repo=${REPO}" 2>/dev/null | tail -n 1 
    # get the actual status.
    CI_STATUS=$(curl -s https://dash.hackedyour.info/api/status 2>/dev/null | jq -r '.[] | select(.provider == "github" and .owner == "adamoutler" and .repo == "gemini-webui") | .status')

    if [ "$CI_STATUS" = "failed" ] || [ "$CI_STATUS" = "failure" ]; then
        CI_LOGS=$(curl -s "https://dash.hackedyour.info/api/logs?provider=github&owner=${OWNER}&repo=${REPO}" 2>/dev/null)
        LAST_LINES=$(echo "$CI_LOGS" | jq -r '.log // empty' | tail -n 30)
        jq -n -c --arg status "$CI_STATUS" --arg logs "$LAST_LINES" \
          '{"decision": "deny", "reason":"❌ CI/CD FAILURE", "hookSpecificOutput": {"hookEventName": "AfterTool", "additionalContext": "CRITICAL ALERT: The CI/CD build has FAILED. Per your core mandates, you MUST halt all current tasks, immediately fetch the logs, and fix the broken build. A broken build is an emergency.\nLast 30 lines of log:\n\($logs)\n❌ CI results: \($status)"}}'
    else
        jq -n -c --arg status "$CI_STATUS" \
          '{"decision": "allow", "hookSpecificOutput": {"hookEventName": "AfterTool", "additionalContext": "CI results: \($status)"}}'
    fi
    exit 0
fi
# Proceed normally
echo '{"decision": "allow"}'

