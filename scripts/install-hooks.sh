#!/bin/sh
# Install the history-guard hook. Run once per clone: sh scripts/install-hooks.sh
set -e
root=$(git rev-parse --show-toplevel)
cp "$root/scripts/check-commit-msg.py" "$root/.git/hooks/commit-msg"
chmod +x "$root/.git/hooks/commit-msg"
echo "installed commit-msg hook: a commit naming a private scan identifier is refused."
