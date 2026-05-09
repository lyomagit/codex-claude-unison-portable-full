#!/usr/bin/env python3
from __future__ import annotations

from common import (
    FAILURE_MESSAGE,
    assistant_claims_success,
    assistant_reports_failure,
    event_indicates_provider_issue,
    increment_stop_block_count,
    json_print,
    latest_failure,
    load_turn_state,
    read_event,
    repo_from_event,
    safe_run,
    unresolved_turn_failure,
)

MAX_STRICT_STOP_BLOCKS_PER_TURN = 1


def main() -> int:
    event = read_event()
    if event.get("_unison_error") in {"stdin_too_large", "invalid_json"}:
        return 0
    repo_root = repo_from_event(event)
    turn_id = str(event.get("turn_id") or "")
    last_message = (event.get("last_assistant_message") or "").strip()

    if not turn_id or not last_message:
        return 0
    if event_indicates_provider_issue(event):
        # Provider/runtime failures are outside the shell-failure sentinel. Do not
        # turn them into self-retry loops; the agent should report them plainly.
        return 0

    state = load_turn_state(repo_root, turn_id)
    if not unresolved_turn_failure(state):
        return 0
    claims_success = assistant_claims_success(last_message)
    reports_failure = assistant_reports_failure(last_message)
    if reports_failure:
        return 0
    if not claims_success:
        return 0

    prior_blocks = int(state.get("stop_block_count") or 0)
    if prior_blocks >= MAX_STRICT_STOP_BLOCKS_PER_TURN or event.get("stop_hook_active"):
        # Circuit breaker: one strict continuation is enough evidence. Returning
        # 0 avoids a stop-hook death spiral if the runtime keeps replaying the
        # same assistant message or the model cannot repair the claim.
        return 0

    failure = latest_failure(state) or {}
    failing_command = failure.get("command") if isinstance(failure, dict) else None
    exit_code = failure.get("exit_code") if isinstance(failure, dict) else None
    source = failure.get("exit_code_source") if isinstance(failure, dict) else None
    summary = (failure.get("summary") or "") if isinstance(failure, dict) else ""

    reason = FAILURE_MESSAGE
    if failing_command:
        reason += f" Command: {failing_command}."
    if exit_code is not None:
        reason += f" Exit code: {exit_code} ({source or 'unknown'})."
    if summary:
        reason += f" Output excerpt: {str(summary)[:240]}"

    increment_stop_block_count(repo_root, state)

    json_print(
        {
            "decision": "block",
            "reason": reason,
            "systemMessage": FAILURE_MESSAGE,
        }
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(safe_run(main))
