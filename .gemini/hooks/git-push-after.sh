#!/bin/bash
# Read input from Gemini CLI
INPUT=$(cat)

tool_name=$(echo "$INPUT" | jq -r '.tool_name')

if [[ "$tool_name" =~ run_shell_command|Bash|shell ]]; then
    command=$(echo "$INPUT" | jq -r '.tool_input.command')

    if [[ "$command" =~ git[[:space:]]+push ]]; then
        if [ "$(hostname)" = "inferrence1" ]; then
            echo "Detected git push on inferrence1. Restarting docker-compose in the background..." >&2
            # Automatically recreate the docker container in the background
            # nohup detaches the process from the terminal/current shell and & puts it in the background
            nohup bash -c "docker compose up -d --build --force-recreate" > /dev/null 2>&1 &
        fi
        
        echo "Waiting 20 seconds for GitHub Actions to register the build..." >&2
        sleep 20
        
        CURRENT_COMMIT=$(git rev-parse HEAD)
        RUN_ID=$(gh run list --commit "$CURRENT_COMMIT" --json databaseId -q '.[0].databaseId')
        
        if [ -n "$RUN_ID" ] && [ "$RUN_ID" != "null" ]; then
            echo "Found workflow run $RUN_ID. Watching for completion..." >&2
            
            # Watch the run and stream output to stderr so the user sees it without breaking JSON hook protocol
            gh run watch "$RUN_ID" >&2
            
            # Get final status with polling
            STATUS=""
            ATTEMPTS=0
            while [[ -z "$STATUS" || "$STATUS" == "null" ]] && [[ $ATTEMPTS -lt 6 ]]; do
                STATUS=$(gh run view "$RUN_ID" --json conclusion -q '.conclusion')
                if [[ -z "$STATUS" || "$STATUS" == "null" ]]; then
                    sleep 5
                    ATTEMPTS=$((ATTEMPTS+1))
                fi
            done
            
            if [ "$STATUS" = "failure" ]; then
                LOG_FILE="/tmp/github_run_${RUN_ID}_failed.log"
                gh run view "$RUN_ID" --log-failed > "$LOG_FILE"
                LAST_LINES=$(tail -n 30 "$LOG_FILE")
                jq -n -c --arg result "GitHub Actions workflow run $RUN_ID failed! Log saved to $LOG_FILE. Last 30 lines:\n$LAST_LINES" \
                  '{"decision": "allow", "hookSpecificOutput": {"additionalContext": $result}}'
            else
                jq -n -c --arg result "GitHub Actions workflow run $RUN_ID for commit $CURRENT_COMMIT finished with status: $STATUS" \
                  '{"decision": "allow", "hookSpecificOutput": {"additionalContext": $result}}'
            fi
            exit 0
        else
            jq -n -c '{decision: "allow", "hookSpecificOutput": {"additionalContext": "Could not find a GitHub Actions run for the pushed commit."}}'
            exit 0
        fi
    fi
fi

# Proceed normally
echo '{"decision": "allow"}'
# Test comment to trigger build
