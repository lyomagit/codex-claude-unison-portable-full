#!/usr/bin/env python3
from __future__ import annotations

from common import (
    bootstrap_missing_or_stale,
    json_print,
    managed_profile_exists,
    read_event,
    repo_from_event,
    reset_turn_state,
    safe_run,
)


def main() -> int:
    event = read_event()
    repo_root = repo_from_event(event)
    turn_id = str(event.get("turn_id") or "")
    if turn_id:
        reset_turn_state(repo_root, turn_id)

    messages = []
    if bootstrap_missing_or_stale(repo_root):
        messages.append(
            "This workspace contains the Codex-Claude Unison bundle but it is not bootstrapped or is stale. Read HOW_TO.md, run the portable bootstrap, then read .codex-hybrid/profile.md before non-trivial work."
        )
    elif managed_profile_exists(repo_root):
        messages.append(
            "Read .codex-hybrid/profile.md before planning, editing, or reporting."
        )
    if not messages:
        return 0
    json_print(
        {
            "hookSpecificOutput": {
                "hookEventName": event.get("hook_event_name") or "SessionStart",
                "additionalContext": " ".join(messages),
            },
            "systemMessage": messages[0],
        }
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(safe_run(main))
