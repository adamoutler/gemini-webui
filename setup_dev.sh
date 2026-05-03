#!/bin/bash
set -e

VENV_DIR=".venv"

echo "Creating virtual environment in $VENV_DIR..."
python3 -m venv "$VENV_DIR"

echo "Updating pip..."
"$VENV_DIR/bin/pip" install --upgrade pip

echo "Installing application dependencies..."
"$VENV_DIR/bin/pip" install -r requirements.txt

echo "Installing testing dependencies..."
"$VENV_DIR/bin/pip" install -r requirements-test.txt

# Fix for intermittent Azure Ubuntu mirror timeouts on GitHub Actions
if [ "$CI" = "true" ]; then
    echo "Running in CI: Switching apt mirrors from azure to archive.ubuntu.com to prevent timeouts..."
    sudo sed -i 's/azure.archive.ubuntu.com/archive.ubuntu.com/g' /etc/apt/sources.list || true
    sudo apt-get update || true
fi

echo "Installing Playwright browsers..."
"$VENV_DIR/bin/playwright" install --with-deps chromium webkit

echo "Configuring git hooks..."

echo "Injecting git push interceptor into virtual environment..."
cat << 'EOF' >> "$VENV_DIR/bin/activate"

# Intercept git push to automatically wait for deployment receipt
git() {
    if [ "$1" = "push" ]; then
        command git "$@"
        local push_exit_code=$?
        if [ $push_exit_code -eq 0 ]; then
            if [ -x "./jenkins/wait-for-receipt.sh" ]; then
                ./jenkins/wait-for-receipt.sh
            else
                echo "Warning: ./jenkins/wait-for-receipt.sh not found or not executable."
            fi
        fi
        return $push_exit_code
    else
        command git "$@"
    fi
}
EOF

echo "Setup complete! To activate your environment, run: source $VENV_DIR/bin/activate"
