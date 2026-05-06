# Plan handoff template

Use this for large tasks where implementation should survive a context clear or handoff. Do not force it for small tasks.

## Save this to a plan file

Suggested path:

```text
.codex-hybrid/plans/YYYYMMDD-short-task-name.md
```

Template:

```markdown
# Plan handoff: <task name>

## Latest user request
<Exact current objective in your own words.>

## Constraints and non-goals
- <Constraint>
- <Explicit non-goal>

## Current state
- Modified files: <paths>
- Files read/opened: <paths>
- Persisted tool results: <paths>
- Active servers/processes/ports: <details or none>
- Unresolved failures: <command + exit code or none>

## Implementation plan
1. <Concrete step>
2. <Concrete step>
3. <Concrete step>

## Verification plan
- <Command/check>
- <Command/check>

## Next turn prompt
Implement the following plan: <absolute plan path>. Continue from the latest user request. Reopen modified files before editing, reopen persisted tool results only when needed, and do not claim success until verification is run or explicitly reported as skipped.
```

## Optional context clear

After saving the plan, the user may clear or compact context. The next turn should start from the plan file path, the current verification state, and any transcript/summary path available.
