# Codex-Claude Unison Hooks v3.1 / v3.1.1 Audit

## Purpose

The v3.1 hook layer exists to enforce one narrow production invariant:

```text
A real non-zero shell failure must not be reported as success.
```

The hooks are not a sandbox, not a complete security boundary, and not a replacement for user judgment. They are deterministic guardrails that should be accurate enough to help the agent while conservative enough not to interrupt legitimate work.

## Hook files

- `.codex/hooks/common.py` — shared parsing, event handling, exit-code resolution, transcript lookup, expected-nonzero classification, verification classification, risk classification, provider/runtime skip logic, and turn state.
- `.codex/hooks/pre_tool_use_guard.py` — preflight command-risk classifier for shell tool calls.
- `.codex/hooks/post_tool_use_guard.py` — records command outcomes and injects failure context only for real non-zero shell failures.
- `.codex/hooks/stop_turn_guard.py` — blocks one false success claim while a real shell failure remains unresolved.
- `.codex/hooks/context_hook.py` — resets per-turn state and injects bootstrap/profile reminders.
- `.codex/hooks/tests/run_fixtures.py` — portable in-process fixtures covering false positives, real failures, state clearing, loop guard, provider skip, and preflight risk decisions. The source verifier still compiles every hook script.

Legacy hook names are managed as obsolete package artifacts and are pruned or removed by bootstrap while unrelated user hooks are preserved.

## Design rules

### 1. Exit code is the source of truth

A command is a real failure only when there is exit-code evidence:

1. a strong process-like key in `tool_response`: `exit_code`, `exitCode`, `returncode`, `return_code`, or `returnCode`;
2. otherwise, a matching transcript `exec_command_end` event by `tool_use_id`.

Weak keys such as `status`, `statusCode`, and `code` are accepted only in process-shaped transcript records, not arbitrary application JSON. This prevents responses such as `{"status": 404}` or `{"code": 1}` from becoming fake shell failures.

### 2. Stdout/stderr words are never failure evidence by themselves

Strings such as `failed`, `Traceback`, `Request failed`, `error`, or `No such file` can appear inside docs, fixtures, binaries, examples, or successful search output. v3 uses stdout/stderr only for summaries after exit-code evidence exists.

### 3. Expected probe non-zero is informational

Exit code `1` is allowed for known probe/search commands where `1` commonly means “no match” or “condition false”:

- `grep`, `egrep`, `fgrep`, `rg`, `ripgrep`, `findstr`, `Select-String`;
- `which`, `where`, `pgrep`, `command -v`, `type -P`, `type -Path`;
- `test`, `[`, `[[`;
- `cmp -s`, `cmp --silent`, `cmp --quiet`;
- `diff --quiet`, `diff -q`, `diff --brief`;
- `git grep`;
- `git diff --quiet`, `git diff -q`, `git diff --exit-code`.

The classifier understands common shell wrappers and runners so that `bash -lc 'grep -q missing file'`, `git -C repo diff --quiet`, and similar forms behave correctly.

### 4. Preflight denial is reserved for catastrophic or shared-state risk

Hard denials are limited to commands with high blast radius:

- recursive forced deletion of broad system/home/root paths, including POSIX, Windows cmd, and PowerShell forms;
- recursive deletion of `.git` metadata;
- force-push / forced refspec git pushes;
- filesystem formatting commands such as `mkfs`;
- raw device writes through `dd of=/dev/...`, shell redirection, `tee`, or Windows physical-drive targets;
- recursive `chmod` / `chown` / `chgrp` against broad system/home/root paths;
- power-control commands such as `shutdown`, `reboot`, `poweroff`, `halt`, `Stop-Computer`, or `Restart-Computer`.

Warning-only risks do not block the tool call:

- `git reset --hard`;
- `git clean -fd...`;
- recursive forced deletion of a scoped absolute/home project path;
- `dd of=<ordinary file>`;
- remote download piped into an interpreter such as `curl ... | sh`.

This split is deliberate. A warning reminds the agent to justify or report a risky action without breaking normal repository maintenance, cleanup, or recovery workflows. For example, `/home/alice` is broad and denied, while `/home/alice/project/build` is scoped and warned.

### 5. Preflight classification is shell-aware but not a shell implementation

v3.1 tokenizes shallow shell segments, respects quotes, and recursively inspects common inner commands:

- `bash -c`, `bash -lc`, `sh -c`, `zsh -c`, `dash -c`, `fish -c`;
- `cmd /c`;
- PowerShell / pwsh `-Command`;
- executable command substitutions such as `$(...)` and backticks when they are not inside single-quoted data;
- `uv run`, `poetry run`, `pipenv run`, `npx`, `npm exec`, `pnpm exec`, `yarn exec`;
- common wrappers such as `sudo`, `doas`, `env`, `command`, `builtin`, `time`, `nohup`, `timeout`, and `nice`.

It intentionally avoids matching dangerous words inside quoted search or documentation strings, for example:

```bash
rg 'rm -rf /' docs
printf '%s\n' 'git reset --hard'
grep -R 'shutdown now' docs
```

Those commands are allowed because the dangerous text is data, not the executed operation.

### 6. Uninspectable events fail open

Oversized, malformed, or unsupported hook events do not cause denial or failure recording. A guardrail should not become a reliability hazard merely because the runtime emitted a payload the hook cannot inspect.

### 7. Stop-hook block is narrow and bounded

The Stop hook blocks only when all of these are true:

1. the current turn has an unresolved real non-zero shell failure;
2. the assistant's final message claims success;
3. the assistant does not plainly report the unresolved failure;
4. the Stop hook has not already issued its one strict block for this turn.

After one strict block, the circuit breaker allows the turn to finish to avoid runtime/model death spirals. Durable project behavior remains: fix and re-verify, or report the failure honestly.

### 8. Provider/runtime errors are separate from shell failures

Provider, API, network, rate-limit, context-overflow, authentication, and timeout errors are not shell-command failures. The Stop hook skips shell-failure enforcement only when explicit error-like event fields indicate such a provider/runtime issue. It does not skip enforcement merely because the assistant message mentions a word like “timeout”.

## Turn state

Per-turn state is written under:

```text
.codex-hybrid/guard/unison_turn_state.v3.json
```

The schema stores:

- `command_seq` — monotonic command sequence number;
- `commands` — bounded recent command log;
- `last_failure_seq` — sequence number of the latest real failure;
- `last_successful_verification_seq` — sequence number of the latest successful verification command;
- `stop_block_count` — loop guard counter.

Using monotonic sequence numbers avoids the older truncated-list-index problem where a failure pointer could drift after command-log compaction.

## Verification commands recognized

Successful verification clears an unresolved failure only when the command is a conservative verification command, including:

- `python3 tools/verify_bundle.py --json`;
- `pytest`, `python -m pytest`, `unittest`, `py_compile`, `compileall`;
- `ruff`, `flake8`, `mypy`, `pyright`, `eslint`, `stylelint`, `biome`, `tsc`;
- `npm test`, `npm run test`, `npm run build`, `pnpm`, `yarn`, and `bun` test/build/lint forms;
- `cargo test/check/build/clippy`;
- `go test/vet/build`;
- `dotnet test/build`;
- Maven/Gradle test/check/build/verify/package forms;
- `make test`, `make check`, `make lint`, `make build`, `ninja test`, and similar explicit targets;
- package/runner-wrapped variants such as `uv run pytest`, `poetry run python -m pytest`, and `npx vitest`.

## Fixture coverage

The v3 fixture suite covers:

- exit-zero with scary stdout/stderr;
- real non-zero failure block;
- empty `tool_response` with transcript fallback;
- grep/rg/search no-match expected exit `1`;
- shell-wrapper expected non-zero;
- application JSON `status`/`code` false positives;
- weak transcript exit-code fallback;
- project verifier success clearing unresolved failure;
- turn-state truncation safety;
- honest failure reports vs false success claims;
- stricter Stop-hook honest-failure wording, including past-failure-plus-success claims;
- provider skip narrowing and generic `status` false-positive prevention;
- oversized stdin handling;
- quoted dangerous text in safe search/doc commands;
- executable command substitution denial;
- shell-wrapped catastrophic commands;
- warning-only risky git cleanup/reset;
- scoped home-path warning instead of broad false-positive denial;
- Windows cmd and PowerShell destructive delete forms;
- raw-device redirection and `tee` denial;
- remote-download-to-interpreter warning;
- common command wrappers such as `command`, `timeout`, and `nice`;
- git global options and force-push refspecs;
- installer config regression for `multi_agent_v2` and legacy `[agents]` defaults;
- safer `hooks.json` pruning that preserves unrelated same-filename hooks.

Run from the archive root:

```bash
python3 .codex/hooks/tests/run_fixtures.py -v
python3 tools/verify_bundle.py --json
```

## Known boundaries

- Hooks run only where the active Codex runtime supports them and where `[features].codex_hooks = true` is enabled.
- PreToolUse can deny before a shell command runs, but it cannot be a full shell/security parser.
- PostToolUse runs after command execution and cannot undo side effects; it can only record results and inject context.
- Stop hook continuation behavior is runtime-dependent; v3 therefore keeps one strict block plus a circuit breaker.
- Native Windows Codex hook execution must still be verified on the target runtime. The package includes PowerShell/cmd wrappers and path-quoting tests, but Linux sandbox verification is not a Windows runtime test.
