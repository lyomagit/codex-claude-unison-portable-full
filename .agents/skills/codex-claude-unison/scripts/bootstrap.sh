#!/bin/sh
set -eu
SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
if command -v python3 >/dev/null 2>&1; then
  exec python3 "$SCRIPT_DIR/bootstrap_portable.py" "$@"
fi
if command -v python >/dev/null 2>&1; then
  exec python "$SCRIPT_DIR/bootstrap_portable.py" "$@"
fi
echo "python3 or python is required for Codex-Claude Unison bootstrap." >&2
exit 1
