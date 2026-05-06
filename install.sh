#!/usr/bin/env sh
set -eu
SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
PYTHON=${PYTHON:-python3}
if ! command -v "$PYTHON" >/dev/null 2>&1; then
  if command -v python >/dev/null 2>&1; then
    PYTHON=python
  else
    echo "Python 3.9+ is required." >&2
    exit 1
  fi
fi
exec "$PYTHON" "$SCRIPT_DIR/.agents/skills/codex-claude-unison/scripts/bootstrap_portable.py" --mode auto --target "$PWD" --replace-existing --yes "$@"
