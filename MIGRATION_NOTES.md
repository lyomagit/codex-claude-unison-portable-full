# Migration notes for Codex-Claude Unison v2.3

## Summary

v2.3 converts Codex-Claude Unison from a behavior patch into a full replacement package. It includes backup-first migration, legacy alias detection, hook/config pruning, root install wrappers, full installer fixtures, and source/archive verification.

## Canonical identity

The canonical package identity is now always:

```text
codex-claude-unison
```

Old names such as `codex-claude-hybrid`, `codex-claude-unison-hooks`, `codex-claude-unison-portable`, and `codex-claude-unison-portable-full` are treated as legacy aliases for detection and replacement only.

## What gets backed up

When `--replace-existing` is used, the installer backs up managed files before overwriting or removing them. Repo backups go to:

```text
.codex-hybrid/backups/YYYYMMDDTHHMMSSZ-pre-v2.3/
```

Global backups go to:

```text
~/.codex/backups/YYYYMMDDTHHMMSSZ-pre-v2.3/
```

Every backup contains `backup_manifest.json` with original path, backup path, file size, SHA256, whether the item was a directory, and the planned action.

## Replacement rules

- `AGENTS.md`: user content is preserved; old managed blocks are removed; exactly one current managed block is appended.
- Skills: old managed alias skill dirs are removed after backup; the full skill is installed under `.agents/skills/codex-claude-unison/` or `~/.agents/skills/codex-claude-unison/`.
- Hooks: old package hook entries are pruned from `hooks.json`; unrelated user hooks are preserved.
- Custom agents: old managed `hybrid-*.toml` files are removed after backup; new canonical `unison-*.toml` files are installed.
- Config: unrelated user config is preserved. `codex_hooks=true` is added only when hooks are installed. Legacy `agents.max_threads/max_depth` is removed only when `multi_agent_v2=true`.

## Verification added

The source verifier now includes installer tests for:

- hook-enabled repo install;
- hookless repo install;
- replacement from a fake old/partial install;
- idempotence;
- config regression;
- dry-run non-mutation;
- Windows path quoting review.

Windows runtime hook execution remains a local Codex runtime question; this package unit-tests path handling and provides PowerShell/cmd wrappers.
