#!/bin/bash
# Reset LabOS to fresh state for demo recording
LAB_DIR="$HOME/.openclaw/workspace/lab"
REPO_DIR="/tmp/LabOS"

echo "Cleaning LabOS for demo..."
rm -f "$LAB_DIR/LAB_CONFIG.json"
rm -f "$REPO_DIR/LAB_CONFIG.json"
rm -f "$LAB_DIR/LAB_MEMORY.md"
rm -f "$REPO_DIR/LAB_MEMORY.md"
echo '{"xp": 0, "level": 1, "badges": [], "history": []}' > "$LAB_DIR/xp.json"
rm -rf "$LAB_DIR/data/projects/"*
rm -f "$LAB_DIR/data/active_project.txt"
rm -rf "$LAB_DIR/data/agents/"*/memory.md
rm -rf "$REPO_DIR/data/projects/"*
rm -f "$REPO_DIR/data/active_project.txt"
echo "Done! Open with ?reset to clear browser cache"
