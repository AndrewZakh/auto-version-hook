#!/bin/sh
# Install auto-version-hook as a plain git pre-commit hook.
#
# Usage: ./scripts/install.sh [repo-path]
# (default: the repository containing the current directory)
#
# Requires the `auto-version-hook` command to be on PATH (pip install .).

set -eu

REPO_DIR=${1:-$(git rev-parse --show-toplevel)}
HOOK_PATH=$(git -C "$REPO_DIR" rev-parse --git-path hooks/pre-commit)

if [ -f "$HOOK_PATH" ]; then
    cp "$HOOK_PATH" "$HOOK_PATH.bak"
    echo "existing pre-commit hook backed up to $HOOK_PATH.bak"
fi

cat > "$HOOK_PATH" <<'EOF'
#!/bin/sh
# installed by auto-version-hook
exec auto-version-hook "$@"
EOF
chmod +x "$HOOK_PATH"
echo "installed pre-commit hook: $HOOK_PATH"
