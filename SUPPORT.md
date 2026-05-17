# Support

For setup help, start with these files:

1. `README.md` for the overview.
2. `HOW_TO.md` for installation and verification.
3. `PRODUCTION_READINESS.md` for release and platform notes.
4. `CHANGELOG.md` for version history.

## Before opening an issue

Please run:

```bash
python3 tools/verify_bundle.py --json
```

Then include:

- operating system;
- Python version;
- Codex runtime or app version if known;
- whether hooks are enabled or hookless mode was used;
- installer command;
- verifier output;
- expected behavior;
- actual behavior.

## What belongs in issues

Use GitHub issues for:

- installation problems;
- unexpected hook decisions;
- portability bugs;
- verifier failures;
- documentation gaps;
- feature proposals that preserve the project contract.

## Keep reports safe

Please do not post secrets, private repository contents, or long raw logs. Use redacted snippets or attach minimal reproductions.
