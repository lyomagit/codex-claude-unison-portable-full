# Contributing

Thank you for helping improve Codex-Claude Unison.

This project is a production behavior and tooling layer for Codex. Contributions should preserve the core contract: read before edit, smallest correct change, verify before success, backup before replacement, hookless valid mode, and cross-platform installation.

## Contribution priorities

High-value contributions usually fall into one of these areas:

- reducing false positives in hook policy;
- improving coverage for real risk patterns and misleading agent behavior;
- improving installer idempotence and backup behavior;
- improving Windows, Termux, macOS, and Linux portability;
- strengthening verification fixtures;
- making the docs clearer for operators.

## Rules for hook changes

Hook changes must be evidence-based.

Do not add raw keyword blocking for scary words in stdout or command text. The project distinguishes between executable actions, quoted text, documentation, search patterns, expected probe exits, and real failures.

Every new blocking rule should include:

1. the failure mode it prevents;
2. why it is not a normal legitimate workflow;
3. at least one fixture that should be blocked;
4. at least one nearby legitimate fixture that should be allowed or warning-only.

## Verification before opening a PR

Run:

```bash
python3 tools/verify_bundle.py --json
```

For focused hook work, also run:

```bash
python3 .codex/hooks/tests/run_fixtures.py -v
```

For installer work, also run:

```bash
python3 tools/tests/run_installer_fixtures.py -v
```

For helper tools, also run:

```bash
python3 tools/tests/run_tool_fixtures.py -v
```

If a check fails, do not present the work as verified. Include the exact failing command and result in the PR body.

## PR expectations

A good PR includes:

- concise problem statement;
- file-level summary of changes;
- verification commands and exact results;
- compatibility notes for macOS, Linux, Termux, Windows PowerShell, and Windows cmd when relevant;
- explicit note if native Windows Codex runtime was not tested.

## Backwards compatibility

Preserve hookless installs. Preserve user content during replacement. Do not remove unmanaged hooks, custom config, or user-owned `AGENTS.md` content.

## Sensitive changes

For sensitive changes, avoid publishing copy-paste risky command fragments in issue titles or docs. Use redacted examples where possible and keep the fixture suite as the executable source of truth.
