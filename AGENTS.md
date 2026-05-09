<!-- codex-claude-unison:start -->
# Codex-Claude Unison

This repository contains or has installed the `codex-claude-unison` replacement behavior layer.

## Bootstrap contract

If `.codex-hybrid/bootstrap.state.json` is missing, stale, or not `2026-05-09-v3.1`, read `HOW_TO.md` and run the portable bootstrap before non-trivial work. Use `--replace-existing` so old managed Unison/hybrid installs are backed up and replaced safely.

## Core behavior

- Read before editing.
- Make the smallest correct change.
- Do not add unrelated features, cleanup, abstractions, or compatibility shims unless requested.
- Verify with the most direct available check before claiming completion.
- Report verified, inferred, unverified, and failed results distinctly.
- If a shell command really exits non-zero, treat it as unresolved until it is fixed and re-verified or reported plainly.
- Do not treat scary stdout/stderr words as failure evidence when the exit code is zero or unknown.
- Treat pre-hook warnings as visible risk guidance, not as command failures. Address the risk or report it; do not claim the warning proves success or failure.
- Prefer dedicated tools over shell when tool parity exists.
- Use short, clear updates at meaningful milestones.

## Context hygiene

- Persist huge command/tool outputs with `tools/persist_tool_result.py` instead of flooding context.
- Use `tools/context_doctor.py` when context is bloated; never auto-delete from its report.
- Compaction is lossy. Before compacting, preserve current user request, modified files, files read, commands and outcomes, unresolved failures, plan/task state, verification state, active processes/ports, durable decisions, persisted tool-result paths, and next concrete step.
- After compaction, read the compact summary, reopen modified files before editing, reopen persisted tool-result files only when needed, reconstruct the current plan, and continue from the latest user request.

## Permission reasoning

Low-risk local reversible work is proactive. Ask before actions with any of these concrete risk reasons:

- destructive filesystem action;
- public or external side effect;
- shared infrastructure change;
- hard-to-reverse git action;
- secret exposure risk;
- network or external upload;
- subagent, background process, or long-running process risk.

When asking, name the reason and provenance: user request, this `AGENTS.md`, hook rule, config rule, or inferred safety risk.

## Long work

For large tasks, save a concrete plan using `docs/plan-handoff-template.md`. You may then clear or compact context and resume from the plan path plus current verification state.

## Model/runtime claims

Do not report model context windows, output limits, cached-token behavior, provider catalogs, or hook support as current facts without checking live runtime evidence. Distinguish input context, max output, usable budget after overhead, cached tokens, and provider-specific catalog claims.
<!-- codex-claude-unison:end -->
