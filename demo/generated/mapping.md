# Mapping example

SOURCE BLOCK | ACTION | TARGET FORM | RATIONALE
--- | --- | --- | ---
`AGENTS.md` | PORT | Managed repo instruction block | Portable engineering discipline.
`.agents/skills/codex-claude-unison/SKILL.md` | PORT | Codex skill | Runtime-native behavior contract.
`.codex/hooks/common.py` | ADAPT | Codex hook helper | Hook lifecycle guardrail; runtime support differs by platform.
`docs/context-hygiene.md` | PORT | Documentation | Lossy compaction and rehydration contract.
`vendor transport details` | DROP | Exclude | Provider-specific implementation detail.
