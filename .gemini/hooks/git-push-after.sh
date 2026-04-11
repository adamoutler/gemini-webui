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
            
            # Get final status
            STATUS=$(gh run view "$RUN_ID" --json conclusion -q '.conclusion')
            
            jq -n -c --arg result "GitHub Actions workflow run $RUN_ID for commit $CURRENT_COMMIT finished with status: $STATUS" \
              '{"decision": "allow", "hookSpecificOutput": {"additionalContext": $result}}'
            exit 0
        else
            jq -n -c '{decision: "allow", "hookSpecificOutput": {"additionalContext": "Could not find a GitHub Actions run for the pushed commit."}}'
            exit 0
        fi
    fi
fi

# Proceed normally
echo '{"decision": "allow"}'
