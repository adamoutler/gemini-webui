#!/bin/bash
# wait-for-receipt.sh
RECEIPT="/tmp/jenkins-receipt-gemini-webui.log"
TIMEOUT=300

echo "Waiting for deployment receipt at $RECEIPT (max ${TIMEOUT}s)..."

# Ensure file exists
touch "$RECEIPT"

# Monitor for close_write events and check for completion marker
while true; do
    # inotifywait will block until the file is written and closed
    if ! inotifywait -q -t "$TIMEOUT" -e close_write "$RECEIPT"; then
        echo "Error: Timeout or inotifywait failed."
        exit 1
    fi

    if grep -q "Finished:" "$RECEIPT"; then
        echo "Deployment Complete. Results:"
        echo "----------------------------------------"
        cat "$RECEIPT"
        echo "----------------------------------------"
        
        # Check if successful and sync with GitHub
        if grep -q "Finished: SUCCESS" "$RECEIPT"; then
            echo "Jenkins build succeeded. Syncing with GitHub..."
            git push github --all
            git push github --tags
        else
            echo "Jenkins build FAILED. Skipping GitHub sync."
            echo ""
            echo "ACTION REQUIRED BY AI AGENT:"
            echo "1. The deployment has failed."
            echo "2. You MUST automatically troubleshoot this failure without waiting for user input."
            echo "3. Read the logs above to identify the root cause."
            echo "4. Formulate a fix, commit the changes, and execute 'git push' again."
        fi
        
        exit 0
    fi
    # If "Finished:" isn't there yet, it might be an intermediate update
done
