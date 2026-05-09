# Codex-Claude Unison v3.1 Production Readiness

## Verdict

v3.1 is intended as the production-ready bundle for `codex-claude-unison` where Codex supports the required instruction, skill, and hook surfaces. The package is still a deterministic guardrail layer, not a security sandbox.

## Production invariants

- Real non-zero shell exits are tracked as unresolved until fixed and reverified or reported honestly.
- Scary stdout/stderr text is never shell-failure evidence by itself.
- PreToolUse hard-denies only catastrophic or shared-state risk; risky but legitimate local work gets warnings.
- Hookless installs are valid when hooks are unsupported or explicitly skipped.
- Replacement installs are backup-first and preserve user content outside managed blocks.
- Verification is reproducible through `python3 tools/verify_bundle.py --json`.

## v3.1 hardening scope

- Shell-aware command classification with `bash -lc`, `cmd /c`, PowerShell `-Command`, runners, command substitutions, and backticks.
- Cross-platform destructive delete coverage for POSIX `rm`, PowerShell `Remove-Item`/aliases, and Windows `rmdir`/`rd` forms.
- Scoped home/project cleanup warning instead of broad denial for paths like `/home/alice/project/build`.
- Raw device write denial through `dd`, shell redirection, and `tee`.
- Remote-download-to-interpreter warning for commands like `curl ... | sh`.
- Stricter Stop-hook honest-failure wording so past failure mentions cannot mask false success.
- Safer provider/runtime skip logic and safer `hooks.json` pruning.

## Required release verification

Run from the archive root:

```bash
python3 tools/verify_bundle.py --json
```

Expected coverage:

- required file presence;
- Python compilation;
- tool fixtures;
- hook fixtures;
- installer fixtures;
- hook-enabled install smoke;
- hookless install smoke;
- replacement migration;
- idempotence;
- dry-run non-mutation;
- config regression;
- referenced-file check.

## Known boundaries

- Native Windows Codex hook runtime must still be verified on the target Windows Codex version.
- Hooks are lifecycle guardrails. They do not replace sandboxing, approval policy, least-privilege filesystem permissions, or user review.
- PreToolUse is intentionally conservative. It is shell-aware, but it is not a full shell parser.
- PostToolUse cannot undo side effects because it runs after the command.
- Stop-hook blocking is bounded to avoid death spirals.
