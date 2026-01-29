#!/bin/bash
# Solibri Autorun Script for macOS
# Usage: ./autorun.sh [autorun_setting.xml]

SOLIBRI_PATH="/Applications/Solibri/Solibri.app/Contents/MacOS/JavaApplicationStub"
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
AUTORUN_FILE="${1:-$SCRIPT_DIR/autorun_setting.xml}"

echo "=============================="
echo "Solibri Autorun is starting..."
echo "=============================="

# Check Solibri installation
if [ ! -f "$SOLIBRI_PATH" ]; then
    echo "Error: Solibri not found at $SOLIBRI_PATH"
    exit 1
fi

# Check autorun configuration
if [ ! -f "$AUTORUN_FILE" ]; then
    echo "Error: Autorun configuration not found: $AUTORUN_FILE"
    exit 1
fi

echo "Launching Solibri, please wait..."
"$SOLIBRI_PATH" --autorun "$AUTORUN_FILE"

echo "=============================="
echo "Solibri execution completed!"
echo "=============================="

