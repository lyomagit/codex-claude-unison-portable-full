#!/usr/bin/env python3
from __future__ import annotations

import re
from common import json_print, read_event, safe_run

DANGEROUS_PATTERNS = [
    (r"\brm\s+-rf\s+/(?:\s|$)", "Refusing destructive filesystem wipe."),
    (r"\bsudo\s+rm\b", "Refusing privileged destructive delete."),
    (r"\bgit\s+reset\s+--hard\b", "Ask before rewriting repository state with git reset --hard."),
    (r"\bgit\s+clean\s+-fdx?\b", "Ask before deleting untracked files with git clean."),
    (r"\bgit\s+push\b.*\s+--force(?:\s|$)", "Ask before force-pushing shared history."),
    (r"\bmkfs(?:\.[a-z0-9]+)?\b", "Refusing filesystem formatting command."),
    (r"\bdd\b\s+.*\bof=", "Refusing raw destructive disk write command."),
    (r"\bshutdown\b|\breboot\b|\bpoweroff\b", "Refusing machine power control command."),
]


def main() -> int:
    event = read_event()
    command = (((event.get("tool_input") or {}).get("command")) or "").strip()
    if not command:
        return 0
    for pattern, reason in DANGEROUS_PATTERNS:
        if re.search(pattern, command, re.IGNORECASE):
            json_print(
                {
                    "hookSpecificOutput": {
                        "hookEventName": "PreToolUse",
                        "permissionDecision": "deny",
                        "permissionDecisionReason": reason,
                    },
                    "systemMessage": reason,
                }
            )
            return 0
    return 0


if __name__ == "__main__":
    raise SystemExit(safe_run(main))
