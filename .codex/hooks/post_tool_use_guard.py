#!/usr/bin/env python3
from __future__ import annotations

from common import (
    FAILURE_MESSAGE,
    command_from_event,
    command_is_verification,
    is_shell_tool_event,
    json_print,
    read_event,
    record_command_result,
    repo_from_event,
    safe_run,
)


def main() -> int:
    event = read_event()
    if event.get("_unison_error") in {"stdin_too_large", "invalid_json"}:
        # Unknown/oversized hook events are not reliable failure evidence.
        return 0
    if not is_shell_tool_event(event):
        return 0
    repo_root = repo_from_event(event)
    turn_id = str(event.get("turn_id") or "")
    command = command_from_event(event)
    tool_response = event.get("tool_response")
    if not command or not turn_id:
        return 0

    state = record_command_result(
        repo_root,
        turn_id,
        command,
        event,
        tool_response,
        is_verification=command_is_verification(command),
    )

    commands = state.get("commands") or []
    current = commands[-1] if commands else None
    if not isinstance(current, dict) or not current.get("failed"):
        return 0

    exit_code = current.get("exit_code")
    source = current.get("exit_code_source") or "unknown"
    summary = (current.get("summary") or "").strip()
    extra = f"{FAILURE_MESSAGE} Failed command: {command}. Exit code: {exit_code} ({source})."
    if summary:
        extra += f" Output excerpt: {summary[:600]}"

    json_print(
        {
            "decision": "block",
            "reason": FAILURE_MESSAGE,
            "hookSpecificOutput": {
                "hookEventName": "PostToolUse",
                "additionalContext": extra,
            },
            "systemMessage": FAILURE_MESSAGE,
        }
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(safe_run(main))
