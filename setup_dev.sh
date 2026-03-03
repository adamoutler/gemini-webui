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
playwright install chromium

echo "Configuring git hooks..."
git config core.hooksPath scripts/hooks
chmod +x scripts/hooks/pre-commit
chmod +x scripts/increment_version.sh

echo "Setup complete! To activate your environment, run: source $VENV_DIR/bin/activate"
