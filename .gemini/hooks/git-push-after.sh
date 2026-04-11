#!/bin/bash
# Read input from Gemini CLI
INPUT=$(cat)

tool_name=$(echo "$INPUT" | jq -r '.tool_name')

if [[ "$tool_name" =~ run_shell_command|Bash|shell ]]; then
    command=$(echo "$INPUT" | jq -r '.tool_input.command')

    if [[ "$command" =~ git[[:space:]]+push ]]; then
        OWNER="adamoutler"
        REPO="gemini-webui"
        
        echo "Waiting 10 seconds for GitHub Actions to register the build..." >&2
        sleep 10
        
        echo "Watching CI status via Dash API..." >&2
        # Use the wait endpoint to stream status and wait for completion
        # Note: We use stderr for the dots/output so it doesn't break the JSON hook protocol
        CI_RESULT=$(curl -N -s "https://dash.hackedyour.info/api/wait?provider=github&owner=${OWNER}&repo=${REPO}" | tee /dev/stderr | tail -n 1)
        
        CI_STATUS=$(echo "$CI_RESULT" | jq -r '.status // empty')
        
        if [ "$CI_STATUS" = "failure" ]; then
            # Fetch failed logs via Dash API
            CI_LOGS=$(curl -s "https://dash.hackedyour.info/api/logs?provider=github&owner=${OWNER}&repo=${REPO}")
            LAST_LINES=$(echo "$CI_LOGS" | jq -r '.log // empty' | tail -n 30)
            
            jq -n -c --arg result "GitHub Actions workflow failed! Last 30 lines of log:\n$LAST_LINES" \
              '{"decision": "allow", "hookSpecificOutput": {"additionalContext": $result}}'
        else
            jq -n -c --arg result "GitHub Actions workflow finished with status: $CI_STATUS" \
              '{"decision": "allow", "hookSpecificOutput": {"additionalContext": $result}}'
        fi
        exit 0
    fi
fi

# Proceed normally
echo '{"decision": "allow"}'
