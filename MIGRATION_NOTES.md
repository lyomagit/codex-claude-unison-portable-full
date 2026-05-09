# Migration notes for Codex-Claude Unison v3.1

## Summary

v3.1 is a production-hardening release for the `codex-claude-unison` replacement package. It keeps the v2 full installer model—backup-first migration, legacy alias detection, managed-block preservation, hook/config pruning, hookless mode, dry-run mode, and source/archive verification—and focuses the upgrade on hook correctness.

The v3.1 goal is simple: hooks should enforce real behavioral invariants without interrupting normal legitimate work. It is a production-readiness release focused on fewer false positives, better cross-shell risk coverage, and safer migration pruning.

## Canonical identity

The canonical package identity remains:

```text
codex-claude-unison
```

Old names such as `codex-claude-hybrid`, `codex-claude-unison-hooks`, `codex-claude-unison-portable`, and `codex-claude-unison-portable-full` are treated as legacy aliases for detection and replacement only.

## What gets backed up

When `--replace-existing` is used, the installer backs up managed files before overwriting or removing them. Repo backups go to:

```text
.codex-hybrid/backups/YYYYMMDDTHHMMSSZ-pre-v3.1/
```

Global backups go to:

```text
~/.codex/backups/YYYYMMDDTHHMMSSZ-pre-v3.1/
```

Every backup contains `backup_manifest.json` with original path, backup path, file size, SHA256, whether the item was a directory, and the planned action.

## Replacement rules

- `AGENTS.md`: user content is preserved; old managed blocks are removed; exactly one current managed block is appended.
- Skills: old managed alias skill dirs are removed after backup; the full skill is installed under `.agents/skills/codex-claude-unison/` or `~/.agents/skills/codex-claude-unison/`.
- Hooks: old package hook entries are pruned from `hooks.json`; unrelated user hooks are preserved.
- Custom agents: old managed `hybrid-*.toml` files are removed after backup; new canonical `unison-*.toml` files are installed.
- Config: unrelated user config is preserved. `codex_hooks=true` is added only when hooks are installed. Legacy `agents.max_threads/max_depth` is removed only when `multi_agent_v2=true`.

## v3.1 hook migration

v3.1 uses a conservative shell-aware classifier rather than raw string matching:

- Dangerous-looking text inside quoted search/doc commands is ignored instead of blocked.
- Executable command substitutions such as `$(rm -rf /)` and backticks are inspected recursively.
- `rm -rf /`, broad system/home/root deletes, recursive `.git` deletion, force-pushes, filesystem formatting, raw device writes, and power-control commands remain hard denials.
- Scoped absolute project cleanups, `git reset --hard`, `git clean -fdx`, ordinary `dd of=file`, and remote-download-to-interpreter pipelines are warning-only. They remain visible to the agent but do not interrupt normal tool access.
- Home-root deletes such as `/home/alice`, `/Users/alice`, and `C:\Users\Alice` deny; deeper scoped paths such as `/home/alice/project/build` warn.
- Windows cmd and PowerShell destructive forms are covered: `Remove-Item -Recurse -Force`, PowerShell `rm`, and `rmdir /s /q` follow the same deny/warn policy.
- Raw device writes through shell redirection and `tee` are denied in addition to `dd of=/dev/...`.
- Oversized or malformed hook events fail open because they are not reliable evidence for denial.
- Exit-code extraction trusts strong process keys in `tool_response`; weak application-like keys are accepted only in process-shaped transcript `exec_command_end` records.
- Expected probe non-zero commands include shell-wrapped and runner-wrapped grep/rg/findstr, `which`, `command -v`, `test`, `cmp`, `diff --quiet`, `git diff --quiet`, and `git grep`.
- Successful project verification with `python3 tools/verify_bundle.py --json` clears unresolved shell-failure state.
- Stop-hook wording is stricter: a generic “fixed the error; done” or “tests failed earlier, now fixed; done” does not count as an honest unresolved-failure report.
- Provider/runtime bypasses require explicit error-like fields and do not trigger on generic `status` text.

## Verification added or strengthened

The source verifier and fixtures now cover:

- hook-enabled repo install;
- hookless repo install;
- replacement from a fake old/partial install;
- idempotence;
- config regression;
- dry-run non-mutation;
- Windows path quoting review;
- shell-wrapped expected non-zero probes;
- application JSON `status`/`code` false-positive prevention;
- transcript weak exit-code fallback;
- project verifier success clearing failure state;
- turn-state truncation safety;
- stricter Stop-hook honest-failure matching;
- provider-error skip narrowing;
- pre-hook quoted dangerous text false-positive prevention;
- common shell wrappers and git global options in risk classification;
- executable command substitution denial;
- scoped home-path warning instead of broad false-positive denial;
- Windows cmd and PowerShell destructive delete forms;
- raw-device redirection and `tee`;
- remote-download-to-interpreter warning;
- safer `hooks.json` pruning that preserves unrelated same-filename hooks.

Windows runtime hook execution remains a local Codex runtime question; this package unit-tests path handling and provides PowerShell/cmd wrappers.
