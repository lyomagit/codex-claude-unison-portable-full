# Retry policy

Retries are useful when they reduce uncertainty. They are harmful when they amplify provider failures, hide command failures, or create loops.

## Classes of failure

- **Command failure:** a local command exited non-zero. Read the error, fix the cause, rerun a relevant verification, or report the failure plainly.
- **Expected probe non-zero:** commands such as `grep` no-match or `git diff --quiet` may return `1` without indicating a broken task.
- **Provider/rate-limit/network failure:** do not spin aggressively. Retry sparingly only if the runtime exposes a safe retry path; otherwise report the interruption.
- **Context overflow:** persist large outputs, run the context doctor, compact with the handoff contract, then continue from the latest request.
- **Permission denial:** do not repeat the same request unchanged. Explain the specific risk or choose a lower-risk route.

## Foreground work

For user-visible operations, one focused retry is acceptable after diagnosing the likely cause. Tell the user what changed if the retry matters.

## Background or maintenance work

Background maintenance should fail quietly or report compactly. Do not create endless recovery loops.

## Heartbeats

For unattended long-running work, send short milestone updates or heartbeat/progress messages instead of silence. Keep them factual: what is running, what has passed, what is blocked.

## Stop-hook loop guard

The shell-failure stop guard may block one false success claim per turn. After that, it avoids repeated hard blocks so the runtime does not spiral. The durable rule remains: do not claim success while a real command failure is unresolved.
