# Changelog

All notable changes for Codex-Claude Unison are summarized here.

This project uses a date-based package version format such as `2026-05-17-v3.1.1`.

## 2026-05-17-v3.1.1

Packaging and public-repository quality release.

### Fixed

- The release archive now includes the MIT license text.
- Python bytecode caches and `__pycache__` directories are excluded from the release archive.
- The verifier now fails if forbidden interpreter/build artifacts are present in the bundle.
- The verifier now checks that license text is present in either source-archive or installed-target form.
- Public history wording was softened to avoid unsupported claims while preserving the early practical guardrail story.

### Changed

- GitHub Actions workflow is prepared for current major actions and cross-platform smoke coverage.
- Repository setup notes are post-release oriented instead of PR-merge oriented.
- Security reporting guidance no longer references an undefined private contact channel.

## 2026-05-09-v3.1

Production-readiness hardening release.

### Added

- GitHub presentation and maintenance docs.
- CI-friendly verification workflow support through `tools/verify_bundle.py --json`.
- Stronger PreToolUse classification for executable shell substitutions, PowerShell, Windows cmd, raw-device write patterns, and remote-download pipelines.
- More precise Stop-hook unresolved-failure handling.
- Safer hook matcher coverage for common Codex shell tool names.

### Changed

- Broad home/root/system deletes remain hard-deny, while scoped project cleanup is warning-only.
- `hooks.json` pruning preserves unrelated hooks with similar filenames unless they are clearly managed Unison hooks.
- Windows wrappers fall back from `py` to `python3`/`python` and quote configured Python paths.

### Verification

- `python3 tools/verify_bundle.py --json` passes on the packaged source tree.
- Hook fixture suite passes.
- Tool fixture suite passes.
- Installer fixture suite passes.
- Clean zip extract verification passes.

Native Windows Codex hook runtime still requires local verification on a Windows host.

## 2026-05-09-v3.0

Major hook semantics hardening release.

### Added

- Shell-aware command classification instead of raw dangerous-string matching.
- Deny/warn distinction for PreToolUse policy.
- Monotonic guard-state sequencing for failure tracking.
- Scoped successful-verification detection.

### Fixed

- Scary stdout/stderr words are not failure evidence without exit-code evidence.
- Successful verifier runs clear unresolved failure state.
- Oversized or malformed hook events fail open instead of blocking legitimate work.

## 2026-04-28-v2.3

Portable full replacement package baseline.

### Added

- Cross-platform installers.
- Backup-first replacement flow.
- Hookless-valid install mode.
- Bundle verifier.
- Context hygiene helpers.
