#!/bin/bash
# wait-for-receipt.sh
RECEIPT="/tmp/jenkins-receipt-gemini-webui.log"
TIMEOUT=600

# 1. Remove the file at the start to ensure we are waiting for a new build
rm -f "$RECEIPT"

echo "Waiting for build to start and finish (max total ${TIMEOUT}s)..."

# Global timeout end time
end_time=$(( SECONDS + TIMEOUT ))

# Wait for "Gemini WebUI Build Started"
started=false
while [ $SECONDS -lt $end_time ]; do
    if [ -f "$RECEIPT" ] && grep -q "Gemini WebUI Build Started" "$RECEIPT" 2>/dev/null; then
        started=true
        echo -e "\nBuild started. Waiting for completion..."
        break
    fi
    if [ $(( SECONDS % 10 )) -eq 0 ]; then
        echo -n "."
    fi
    sleep 2
done

if [ "$started" = false ]; then
    echo -e "\nError: Global timeout reached (${TIMEOUT}s) waiting for build to start."
    exit 1
fi

# Now wait for "Gemini WebUI Build Finished"
finished=false
while [ $SECONDS -lt $end_time ]; do
    if grep -q "Gemini WebUI Build Finished" "$RECEIPT" 2>/dev/null; then
        finished=true
        echo -e "\nDeployment Complete. Results:"
        echo "----------------------------------------"
        cat "$RECEIPT"
        echo "----------------------------------------"

        # Check if successful and sync with GitHub
        if grep -q "Gemini WebUI Build Finished: SUCCESS" "$RECEIPT"; then
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
    if [ $(( SECONDS % 10 )) -eq 0 ]; then
        echo -n "."
    fi
    sleep 2
done

echo -e "\nError: Global timeout reached (${TIMEOUT}s) waiting for build to finish."
exit 1
