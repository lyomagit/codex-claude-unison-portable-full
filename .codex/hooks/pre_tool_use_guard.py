#!/usr/bin/env python3
from __future__ import annotations

from common import (
    classify_command_risks,
    command_from_event,
    is_shell_tool_event,
    json_print,
    read_event,
    repo_from_event,
    safe_run,
    strongest_risk,
)


def main() -> int:
    event = read_event()
    if event.get("_unison_error") == "stdin_too_large":
        # Fail open for oversized hook payloads. A guardrail should not break
        # legitimate large commands/edits when it cannot inspect the event.
        json_print(
            {
                "systemMessage": "Codex-Claude Unison preflight skipped an oversized hook event; no command was denied because the event could not be inspected reliably."
            }
        )
        return 0
    if event.get("_unison_error") == "invalid_json":
        return 0
    if not is_shell_tool_event(event):
        return 0
    command = command_from_event(event)
    if not command:
        return 0

    risks = classify_command_risks(command, repo_from_event(event))
    risk = strongest_risk(risks)
    if risk is None:
        return 0

    if risk.severity == "deny":
        json_print(
            {
                "hookSpecificOutput": {
                    "hookEventName": "PreToolUse",
                    "permissionDecision": "deny",
                    "permissionDecisionReason": risk.reason,
                },
                "systemMessage": risk.reason,
            }
        )
        return 0

    # Warning-only risks keep normal tools usable while preserving a visible
    # deterministic nudge for risky but sometimes legitimate actions.
    json_print({"systemMessage": risk.reason})
    return 0


if __name__ == "__main__":
    raise SystemExit(safe_run(main))
