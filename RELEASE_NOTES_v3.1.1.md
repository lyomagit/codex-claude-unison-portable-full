# Codex-Claude Unison v3.1.1

Packaging and public-repository polish release.

## Highlights

- Release archive now includes MIT license text.
- Python bytecode caches are excluded from the bundle.
- Verifier detects forbidden packaging artifacts.
- Verifier checks license presence.
- GitHub Actions workflow is prepared for current major actions and cross-platform smoke coverage.
- Public docs avoid unsupported historical overclaims.

## Verification

Run from the archive root:

```bash
python3 tools/verify_bundle.py --json
```

Native Windows Codex hook runtime still requires local verification on a Windows host before claiming full Windows runtime validation.
