# Codex-Claude Unison Hooks v2 Audit

## Architecture audit

The hook layer is now a single common-based guard set:

- `.codex/hooks/common.py` — shared parsing, exit-code resolution, transcript lookup, expected-nonzero classification, verification classification, and turn state.
- `.codex/hooks/pre_tool_use_guard.py` — high-risk Bash command denial.
- `.codex/hooks/post_tool_use_guard.py` — records command outcomes and injects the failure sentinel only for real non-zero exits.
- `.codex/hooks/stop_turn_guard.py` — blocks false success claims while a real failure remains unresolved.
- `.codex/hooks/context_hook.py` — resets turn state and injects bootstrap/profile reminders.
- `.codex/hooks/tests/run_fixtures.py` — portable fixture/smoke tests.

Legacy names are treated as obsolete and are pruned from `hooks.json` during bootstrap:

- `pre_tool_use_policy.py`
- `post_tool_use_review.py`
- `stop_enforcer.py`

If those files exist in the target hook directory, bootstrap renames them to `*.disabled-by-codex-claude-unison-v2` instead of deleting them.

## Root cause fixed

The previous PostToolUse guard confused command output with command failure. In `common.py`, `command_failed()` used text heuristics such as `failed`, `Traceback`, `No such file`, `blocked`, and `Error` as failure evidence when `exit_code` was zero or unavailable. This caused false blocks when commands merely printed those words, such as reading a Markdown file or grepping strings from a binary containing `Request failed`.

## New failure source of truth

Failure detection is now ordered as follows:

1. Use structured `tool_response.exit_code` / equivalent numeric exit-code field when present.
2. If missing, look up a matching `exec_command_end` event in the transcript by `tool_use_id`.
3. If no exit code is available, do not block based only on stdout/stderr words.

Stdout/stderr are retained only as a short summary excerpt in the warning payload.

## Expected non-zero handling

Exit code `1` is allowed for expected no-match / difference probes:

- `grep`, `rg`, `ripgrep`, `findstr`
- `test`, `[ ... ]`
- `which`, `command -v`
- `git diff --quiet`
- `cmp`
- `diff --quiet`

Other non-zero exits remain failures.

## Stop hook policy

The Stop hook blocks only when all of these are true:

- the current turn has a real unresolved failure;
- the assistant makes a success claim;
- the assistant does not honestly report the failure.

A later successful verification command clears the unresolved failure. A later exploratory success does not.

## Cross-platform changes

Bootstrap now generates hook commands with `sys.executable` and absolute script paths for the target install. It does not rely on `/usr/bin`, `/opt/homebrew`, `git rev-parse`, `/bin/bash`, GNU coreutils, or macOS-only paths.

Supported install modes:

- repo/workspace install, including non-git directories;
- global install to `~/.codex` and `~/.agents/skills`;
- Termux via `Path.home()`;
- WSL/Linux/macOS via Python or the portable shell wrapper;
- native Windows via Python/py when the active Codex runtime supports hooks;
- no-Python Windows fallback remains hookless and writes AGENTS/profile fallback instructions.

## MultiAgentV2 config fix

A v2.1 installer fix removes the modern Codex conflict where `[features].multi_agent_v2 = true` is combined with legacy `[agents].max_threads` or `[agents].max_depth`. The installer no longer adds those legacy keys by default. If MultiAgentV2 is already enabled, `ensure_codex_config()` deletes `max_threads` and `max_depth`, removes the `[agents]` section if it becomes empty, preserves `multi_agent_v2 = true`, and independently adds `[features].codex_hooks = true` when hooks are enabled.

## v2.2 developer-behavior upgrade

This release adds clean-room, Codex-native developer-workflow helpers inspired by portable behavior patterns only:

- disk-backed large output persistence via `tools/persist_tool_result.py`;
- offline context audit via `tools/context_doctor.py`;
- concise always-on compaction and post-compaction rehydration rules;
- plan-handoff and retry-policy docs;
- typed permission-reason guidance;
- model capability clarity guidance;
- stop-hook circuit breaker to avoid repeated hard-block death spirals during false-success recovery.

The helper tools are optional and dependency-free. Runtime interception of every Codex tool result is not assumed; when hooks/runtime integration cannot enforce a behavior, the bundle documents it as workflow guidance.

## Verification performed

Use these commands from the archive root:

```bash
/usr/bin/python3 -m py_compile .codex/hooks/common.py .codex/hooks/context_hook.py .codex/hooks/pre_tool_use_guard.py .codex/hooks/post_tool_use_guard.py .codex/hooks/stop_turn_guard.py .codex/hooks/tests/run_fixtures.py .agents/skills/codex-claude-unison/scripts/bootstrap_portable.py .agents/skills/codex-claude-unison/scripts/build_hybrid_profile.py tools/persist_tool_result.py tools/context_doctor.py tools/verify_bundle.py tools/tests/run_tool_fixtures.py
/usr/bin/python3 .codex/hooks/tests/run_fixtures.py -v
/usr/bin/python3 tools/tests/run_tool_fixtures.py -v
/usr/bin/python3 tools/verify_bundle.py --json
```

The fixture suite covers:

- exit_code `0` + stdout contains `Request failed` -> no block;
- exit_code `0` + stdout contains `Traceback` -> no block;
- exit_code `1` + empty stdout -> block;
- empty `tool_response` + transcript matching `exec_command_end exit_code=1` -> block;
- empty `tool_response` + transcript matching `exit_code=0` but scary stdout -> no block;
- grep no-match exit `1` -> no block;
- real lint/test/build-style nonzero -> block;
- later successful verification clears unresolved failure;
- honest failure report is allowed by Stop logic;
- false success claim after unresolved failure is blocked;
- PostToolUse smoke tests for scary stdout and real nonzero;
- installer config regression: MultiAgentV2 preserves `multi_agent_v2 = true`, removes legacy `agents.max_threads` / `agents.max_depth`, removes an empty `[agents]`, and adds `codex_hooks = true`.

## v2.3 replacement-package upgrade

v2.3 keeps the v2 shell-failure semantics and adds full replacement behavior:

- backup-first installer with `backup_manifest.json`;
- legacy alias detection for old Unison/hybrid installs;
- managed `AGENTS.md` block replacement without deleting user content;
- pruning old package hook commands from `hooks.json` while preserving unrelated hooks;
- canonical `unison-*.toml` custom agents;
- root `install.sh`, `install.ps1`, and `install.cmd` wrappers;
- `--replace-existing`, `--backup-dir`, `--dry-run`, and machine-readable `--json` support;
- installer fixture tests for hook-enabled install, hookless install, replacement, idempotence, config regression, dry-run, and Windows path quoting.

The hook truth rule is unchanged: only real exit-code evidence, or transcript `exec_command_end` evidence by `tool_use_id`, creates unresolved command failure. Output text alone is never failure evidence.
