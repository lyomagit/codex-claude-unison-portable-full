# Security Policy

Codex-Claude Unison is a Codex behavior and tooling layer. It improves agent discipline and adds guardrails, but it is not an operating-system sandbox and does not replace code review, CI, repository permissions, or host-level isolation.

## Supported versions

| Version | Status |
| --- | --- |
| 2026-05-17-v3.1.1 | Supported |
| 2026-05-09-v3.1 | Upgrade recommended for packaging/license hygiene |
| Earlier v3.x | Best-effort |
| v2.x and older | Upgrade recommended |

## Reporting a vulnerability

If GitHub private vulnerability reporting is enabled for this repository, use it for sensitive reports. Otherwise, open a redacted GitHub issue and avoid including secrets, private repository content, or copy-paste risky command fragments in the title/body.

A useful report includes:

- affected version and commit;
- operating system and Codex runtime details;
- whether hooks were enabled or hookless mode was used;
- exact installer command when relevant;
- verifier output from `python tools/verify_bundle.py --json` or `python3 tools/verify_bundle.py --json`;
- minimal reproduction steps, redacted when needed.

## Security boundaries

This project does not collect telemetry, upload secrets, or make network calls during verification. Treat it as a quality and safety guardrail for agent workflows, not as a complete security boundary.

## Disclosure expectations

Reports that identify a real bypass or false-positive pattern should include regression tests or fixture suggestions when possible. Fixes should preserve legitimate developer workflows and avoid broad keyword-only blocking.
