#!/bin/bash
set -e

VENV_DIR=".venv"

echo "Creating virtual environment in $VENV_DIR..."
python3 -m venv $VENV_DIR

echo "Activating virtual environment..."
source $VENV_DIR/bin/activate

echo "Updating pip..."
pip install --upgrade pip

echo "Installing application dependencies..."
pip install -r requirements.txt

echo "Installing testing dependencies..."
pip install -r requirements-test.txt

echo "Installing Playwright browsers..."
playwright install --with-deps chromium webkit

echo "Configuring git hooks..."
chmod +x scripts/increment_version.sh

echo "Injecting git push interceptor into virtual environment..."
cat << 'EOF' >> $VENV_DIR/bin/activate

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
