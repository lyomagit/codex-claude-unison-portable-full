# Codex-Claude Unison v2.3

A complete, installable, cross-platform replacement package for the Codex-Claude Unison behavior/tooling layer.

The package identity is stable: `codex-claude-unison`.

## Start here

This repository contains the unpacked bundle source and the original release archive:

- unpacked source: this repository root;
- release archive: `codex-claude-unison-portable-full-20260428-v2.3.zip`.

For both a human operator and an AI coding agent, the entrypoint is:

```text
Read HOW_TO.md first.
```

`HOW_TO.md` explains the exact bootstrap command, replacement behavior, hookless mode, dry-run mode, and verification step. Do not start by copying individual files by hand unless you are intentionally doing a manual audit.

Minimal deployment flow:

1. Clone or download this repository.
2. Open `HOW_TO.md`.
3. Run the installer command from `HOW_TO.md` in the workspace where the behavior layer should be installed.
4. After bootstrap, read the generated `.codex-hybrid/profile.md`, `.codex-hybrid/mapping.md`, and `.codex-hybrid/inventory.json`.
5. Run the verification command from `HOW_TO.md` and report any failed check honestly.

If you only have the zip file, extract it first, then follow the same `HOW_TO.md` entrypoint from the extracted directory.

It is designed for one workflow:

```text
Read HOW_TO.md and self-bootstrap this bundle into the current workspace.
```

Codex should then run the portable bootstrap, backup any old managed Unison/hybrid install, replace it with this full package, regenerate `.codex-hybrid/profile.md`, `.codex-hybrid/mapping.md`, and `.codex-hybrid/inventory.json`, and continue the real task under the generated project contract.

## What this package does

It gives Codex a durable engineering discipline layer:

- repo `AGENTS.md` behavior rules;
- the `codex-claude-unison` skill;
- local profile generation under `.codex-hybrid/`;
- optional hooks for shell-failure honesty where the Codex runtime supports hooks;
- custom narrow agent roles;
- context hygiene helpers;
- installer backup, replacement, dry-run, and verification tests.

## The key behavior

Codex must not pretend a failed check succeeded.

If a shell command really exits non-zero, the failure remains unresolved until Codex either fixes it and reruns a relevant verification, or reports the failure plainly. The hooks and instructions do **not** treat scary words in stdout/stderr, such as `failed`, `Traceback`, or `Request failed`, as failure evidence by themselves. The source of truth is a real exit code, with transcript fallback by `tool_use_id` when needed.

## Long-session developer upgrades

This release keeps the v2.2 developer-behavior features and turns the package into a full replacement installer:

- `tools/persist_tool_result.py` stores large command/tool outputs under `.codex-hybrid/tool-results/` and prints a small preview plus the full path.
- `tools/context_doctor.py` audits context bloat and unresolved guard state without deleting anything.
- `docs/context-hygiene.md` defines lossy compaction and post-compaction rehydration rules.
- `docs/retry-policy.md` separates command failures, expected probe non-zero, provider/rate-limit failures, context overflow, and permission denials.
- `docs/plan-handoff-template.md` gives a file-based handoff for large tasks or optional context clear.

## Replacement behavior

The installer detects old managed installs by markers, not only by one exact folder name. It recognizes:

- `codex-claude-unison`, `codex-claude-hybrid`, `codex-claude-unison-hooks`, `codex-claude-unison-portable`, and `codex-claude-unison-portable-full` skill directories or state markers;
- old managed `AGENTS.md` blocks;
- old `HOW_TO.codex-claude-unison.md`, `README.codex-claude-unison.md`, and `HYBRID_MODEL_INSTRUCTIONS.codex-claude-unison.md` docs;
- old hook files such as `post_tool_use_review.py`, `pre_tool_use_policy.py`, and `stop_enforcer.py`;
- old `hooks.json` commands pointing to previous Unison/hybrid hook scripts;
- old `hybrid-*.toml` custom agents when their content identifies them as managed by this package.

Before replacing managed files, it creates a backup such as:

```text
.codex-hybrid/backups/YYYYMMDDTHHMMSSZ-pre-v2.3/
```

For global installs, backups go under `~/.codex/backups/` unless `--backup-dir` is supplied. Each backup includes `backup_manifest.json` with original path, backup path, file size, SHA256, and planned action.

## Install commands

Unix, macOS, Linux, Termux:

```bash
./install.sh --json
```

Windows PowerShell:

```powershell
.\install.ps1 --json
```

Windows cmd:

```cmd
install.cmd --json
```

Direct Python entrypoint:

```bash
python3 .agents/skills/codex-claude-unison/scripts/bootstrap_portable.py --mode auto --target "$PWD" --replace-existing --yes --json
```

Supported flags:

```text
--mode auto|repo|global|both
--target PATH
--source PATH        # repeatable
--skip-hooks
--replace-existing
--backup-dir PATH
--dry-run
--yes
--json
```

`--mode auto` is workspace-first. If the target is in a git repo, it installs at the repo root. If not, it installs into the target workspace. Global install is explicit through `--mode global` or `--mode both`.

## Config compatibility

The installer preserves `[features].multi_agent_v2 = true` and removes legacy `[agents].max_threads` / `[agents].max_depth` only when MultiAgentV2 is enabled, because that combination breaks modern Codex. It never generates those legacy `[agents]` defaults. It adds `[features].codex_hooks = true` only when hooks are installed.

## Verification

From the archive root:

```bash
python3 tools/verify_bundle.py --json
```

The verifier checks required files, Python compilation, hooks, helper tools, installer smoke tests, replacement migration, idempotence, dry-run behavior, config regression, and Windows path quoting logic.

If you install hookless with `--skip-hooks`, the installed repo verifier reads `.codex-hybrid/bootstrap.state.json` and skips hook-file requirements.

## Platform notes

- macOS, Linux, and Termux are supported with Python 3.9+.
- Windows PowerShell and Windows cmd wrappers are included. Native Windows hook behavior remains Codex-runtime dependent.
- The installer does not require Bash on Windows, does not use symlinks, does not call `git rev-parse`, and does not assume GNU coreutils.

## Boundaries

This package is Codex-native and clean-room. It does not add telemetry, GrowthBook, Statsig, plan upsells, engagement loops, or fake “unlimited context” claims. Compaction is treated as lossy. Model/runtime capability claims must be verified before being reported as current facts.
