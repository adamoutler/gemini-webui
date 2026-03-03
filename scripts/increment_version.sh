#!/bin/bash
set -e

# Path to files
VERSION_FILE="VERSION"
MANIFEST_FILE="src/static/manifest.json"
SW_FILE="src/static/sw.js"

# Check if VERSION file exists, if not create it
if [ ! -f "$VERSION_FILE" ]; then
    echo "0.1.0" > "$VERSION_FILE"
fi

# Read current version
current_version=$(cat "$VERSION_FILE" | tr -d '[:space:]')

# Default to 0.1.0 if empty
if [ -z "$current_version" ]; then
    current_version="0.1.0"
fi

# Extract components
major=$(echo "$current_version" | cut -d. -f1)
minor=$(echo "$current_version" | cut -d. -f2)
patch=$(echo "$current_version" | cut -d. -f3)

# Default patch to 0 if not present
if [ -z "$patch" ]; then
    patch=0
fi

# Increment patch
patch=$((patch + 1))
new_version="${major}.${minor}.${patch}"

# Update VERSION file
echo "$new_version" > "$VERSION_FILE"

# Update manifest.json
python3 -c "
import json
import os

manifest_file = '$MANIFEST_FILE'
if os.path.exists(manifest_file):
    with open(manifest_file, 'r') as f:
        data = json.load(f)
    data['version'] = '$new_version'
    with open(manifest_file, 'w') as f:
        json.dump(data, f, indent=2)
        f.write(chr(10))
"

# Update sw.js
python3 -c "
import re
import os

sw_file = '$SW_FILE'
new_version = '$new_version'
if os.path.exists(sw_file):
    with open(sw_file, 'r') as f:
        content = f.read()
    
    # Replace CACHE_NAME pattern
    new_content = re.sub(
        r\"const CACHE_NAME = 'gemini-webui-v[^']*';\",
        f\"const CACHE_NAME = 'gemini-webui-v{new_version}';\",
        content
    )
    
    with open(sw_file, 'w') as f:
        f.write(new_content)
"

# Add changed files to the commit
git add "$VERSION_FILE" "$MANIFEST_FILE" "$SW_FILE"

echo "Version bumped to $new_version"
exit 0
