#!/bin/sh
# retro installer: copies the skill into ~/.claude/skills/retro
set -e

SRC="$(cd "$(dirname "$0")" && pwd)/skill"
DEST="${CLAUDE_CONFIG_DIR:-$HOME/.claude}/skills/retro"

if [ ! -f "$SRC/SKILL.md" ]; then
  echo "retro: skill/SKILL.md not found next to install.sh" >&2
  exit 1
fi

# clean install: never leave stale files from a previous version behind
rm -rf "$DEST"
mkdir -p "$DEST"
cp -R "$SRC/." "$DEST/"
chmod +x "$DEST/scripts/scan.py"

echo "retro installed to $DEST"
echo "open Claude Code in any project and run: /retro"
