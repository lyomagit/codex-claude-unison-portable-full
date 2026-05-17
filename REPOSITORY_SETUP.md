# Repository setup checklist

Use this checklist to keep the public repository aligned with the current release.

## Current public state

- Description should be set.
- Website should point to the latest release page.
- Topics should be set.
- Release assets should include the bundle zip and matching `.sha256`.
- GitHub Packages are not required for this project; release assets are the correct distribution mechanism.

## About sidebar

Repository description:

```text
Production-ready behavior, hooks, and verification layer for OpenAI Codex.
```

Website:

```text
https://github.com/lyomagit/codex-claude-unison-portable-full/releases/tag/v3.1.1
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

Suggested tag:

```text
v3.1.1
```

Suggested release title:

```text
Codex-Claude Unison v3.1.1 packaging and repository polish
```

Suggested release notes:

```markdown
Codex-Claude Unison v3.1.1 is a packaging and public-repository polish release for the Codex behavior, hooks, and verification layer.

Highlights:

- release archive now includes MIT license text;
- Python bytecode caches are excluded from the bundle;
- verifier now detects forbidden packaging artifacts;
- verifier now checks license presence;
- shell command tokenization is host-independent for Windows CI parity;
- GitHub Actions workflow is prepared for current action majors and cross-platform smoke coverage;
- public docs avoid unsupported historical overclaims.

Archive:

- `codex-claude-unison-portable-full-20260517-v3.1.1.zip`

Verification:

- source verifier: pass
- hook fixtures: pass
- installer fixtures: pass
- tool fixtures: pass
- clean archive extract verifier: pass

Native Windows Codex hook runtime should still be verified on a Windows host before claiming full Windows runtime validation.
```

Attach:

- `codex-claude-unison-portable-full-20260517-v3.1.1.zip`
- `codex-claude-unison-portable-full-20260517-v3.1.1.zip.sha256`

## License

The repository uses the MIT License. Keep `LICENSE` in the repository root so GitHub can detect it. Keep `LICENSE.codex-claude-unison` in the bundle/install payload so installations into other repositories do not overwrite a host repository's own license.
