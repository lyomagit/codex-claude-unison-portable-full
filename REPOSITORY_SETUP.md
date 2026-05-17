# Repository setup checklist

Use this checklist after merging the presentation PR.

## About sidebar

Set the repository description to:

```text
Production-ready behavior, hooks, and verification layer for OpenAI Codex.
```

Set the website field to the repository URL or to the latest release page after publishing the release:

```text
https://github.com/lyomagit/codex-claude-unison-portable-full
```

Suggested topics:

```text
codex
openai-codex
codex-hooks
agents-md
ai-coding-agent
agent-tooling
developer-tools
hooks
verification
automation
python
cross-platform
termux
powershell
```

## Release

Create a GitHub release after the CI workflow passes.

Suggested tag:

```text
v3.1
```

Suggested release title:

```text
Codex-Claude Unison v3.1 production hardening
```

Suggested release notes:

```markdown
Codex-Claude Unison v3.1 is a production-readiness hardening release for the Codex behavior, hooks, and verification layer.

Highlights:

- fewer false positives in hook policy;
- stronger coverage for real risk patterns;
- clearer failure-honesty behavior;
- safer backup-first replacement behavior;
- cross-platform installer support for macOS, Linux, Termux, Windows PowerShell, and Windows cmd;
- verifier-first workflow through `python3 tools/verify_bundle.py --json`.

Archive:

- `codex-claude-unison-portable-full-20260509-v3.1.zip`

Verification:

- source verifier: pass
- hook fixtures: pass
- installer fixtures: pass
- tool fixtures: pass
- clean archive extract verifier: pass

Native Windows Codex hook runtime should still be verified on a Windows host before claiming full Windows runtime validation.
```

Attach:

- `codex-claude-unison-portable-full-20260509-v3.1.zip`
- the matching `.sha256` file if available.

## Social preview

GitHub generates social previews automatically when no custom image is set. A custom image can be added later in repository settings.

## License

Choose and add an explicit license before marketing this as reusable open-source software. Do not assume a license retroactively.
