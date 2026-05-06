# Context hygiene and compaction contract

This bundle improves long-running development work by keeping bulky, lossy, or stale material out of the active conversation while preserving enough evidence to continue safely.

## Disk-backed large tool results

When a command or tool output is large, do not paste the full result into chat. Persist it locally and show only a compact reference:

```bash
python3 tools/persist_tool_result.py huge-output.log --label test-run
# or
some-command 2>&1 | python3 tools/persist_tool_result.py --label some-command
```

The helper stores the full output under `.codex-hybrid/tool-results/`, writes sidecar metadata, and prints a short preview with the absolute path, byte count, line count, and SHA256. It never overwrites an existing result file.

Use this when output is repetitive, log-like, or larger than what the model needs immediately. Reopen the saved file only when the next step needs details from it.

## Context doctor

Run a local audit when the session feels bloated, compaction failed, or the agent is about to summarize a long investigation:

```bash
python3 tools/context_doctor.py --root "$PWD"
python3 tools/context_doctor.py --root "$PWD" --json
```

The doctor looks for likely bloat sources: huge logs, persisted tool results, stale generated profiles, bulky runbooks, large memory-like files, and unresolved guard state. It gives concrete actions and rough byte savings where possible. It does not delete or modify files.

## Compaction contract

Compaction is lossy. A compacted handoff must preserve operational state, not chat vibes. Include:

- the current user request and intent;
- modified files;
- files read or opened;
- commands run and their outcomes;
- unresolved real non-zero command failures;
- current plan and task state;
- tests or verification already run;
- active servers, processes, ports, and working directories;
- durable decisions and non-goals;
- persisted tool-result paths;
- the next concrete step.

Do not claim that compaction gives unlimited context. It is a lossy compression step with a recovery plan.

## Post-compaction rehydration

On the first turn after compaction:

1. Read the compact summary.
2. Continue from the latest user request, not an older ghost objective.
3. Reopen referenced modified files before editing.
4. Reopen persisted tool-result files only when needed.
5. Reconstruct the current plan.
6. Verify stale claims before asserting success.

## Model capability clarity

Keep these separate:

- input context window;
- max output tokens;
- usable budget after system/tool overhead;
- cached tokens;
- provider-specific model catalog claims.

Before reporting current model/runtime limits as fact, verify them from live runtime output or current official docs. Do not repeat hardcoded myths.
