# Codex-Claude Unison profile

Generated: 2026-04-17T16:50:21Z
Package version: 2026-04-17
Workspace: `/mnt/data`
Archive root: `/mnt/data/codex-claude-one-archive`

## Source paths
- `/mnt/data/prompts.ts`
- `/mnt/data/system.ts`
- `/mnt/data/systemPromptSections.ts`
- `/mnt/data/outputStyles.ts`
- `/mnt/data/files.ts`
- `/mnt/data/apiLimits.ts`
- `/mnt/data/github-app.ts`
- `/mnt/data/xml.ts`
- `/mnt/data/spinnerVerbs.ts`
- `/mnt/data/turnCompletionVerbs.ts`
- `/mnt/data/errorIds.ts`
- `/mnt/data/betas.ts`
- `/mnt/data/keys.ts`
- `/mnt/data/cyberRiskInstruction.ts`
- `/mnt/data/messages.ts`
- `/mnt/data/toolLimits.ts`
- `/mnt/data/tools.ts`
- `/mnt/data/memdir.ts`
- `/mnt/data/teamMemPrompts.ts`
- `/mnt/data/memoryAge.ts`
- `/mnt/data/paths.ts`
- `/mnt/data/memoryTypes.ts`
- `/mnt/data/memoryScan.ts`
- `/mnt/data/teamMemPaths.ts`
- `/mnt/data/findRelevantMemories.ts`
- `/mnt/data/oauth.ts`
- `/mnt/data/common.ts`
- `/mnt/data/product.ts`

## Profile summary
- Files classified: 28
- PORT: 6
- ADAPT: 9
- DROP: 12
- REVIEW: 1

## Core imported contract
- Read relevant files before proposing or making changes.
- Prefer the smallest correct change over speculative cleanup.
- Verify changed behavior when verification is possible.
- Report verified, inferred, and unverified outcomes distinctly.
- Ask before destructive, public, hard-to-reverse, or shared-state actions.
- Prefer dedicated tools over raw shell when tool parity exists.
- Parallelize only independent, concurrency-safe work.
- Treat memory as non-derivable context, not live truth.
- Verify stale remembered claims against current evidence.
- Behave with curiosity, ownership, and discipline; do not scope-creep.

## High-signal local features detected
- Ask before risky actions
- Binary skip discipline
- Closed memory taxonomy
- Explanatory or learning modes
- Hook lifecycle discipline
- Minimal blast radius
- Parallelize only safe independent work
- Path and traversal safety
- Prefer dedicated tools over shell
- Read before edit
- Role-separated multi-agent work
- Security boundary
- Stale memory caution
- Truthful reporting
- Verify before done

## Highest-value PORT files
- `/mnt/data/prompts.ts` — Read before edit, Minimal blast radius, Verify before done, Truthful reporting, Ask before risky actions, Prefer dedicated tools over shell, Parallelize only safe independent work, Explanatory or learning modes, Hook lifecycle discipline, Role-separated multi-agent work
- `/mnt/data/files.ts` — Path and traversal safety, Binary skip discipline
- `/mnt/data/cyberRiskInstruction.ts` — Security boundary
- `/mnt/data/paths.ts` — Path and traversal safety, Hook lifecycle discipline, Role-separated multi-agent work
- `/mnt/data/memoryScan.ts`
- `/mnt/data/teamMemPaths.ts` — Path and traversal safety

## Highest-value ADAPT files
- `/mnt/data/outputStyles.ts` — Explanatory or learning modes
- `/mnt/data/apiLimits.ts`
- `/mnt/data/xml.ts` — Parallelize only safe independent work, Role-separated multi-agent work
- `/mnt/data/toolLimits.ts` — Parallelize only safe independent work
- `/mnt/data/tools.ts` — Hook lifecycle discipline, Role-separated multi-agent work
- `/mnt/data/memdir.ts` — Hook lifecycle discipline
- `/mnt/data/teamMemPrompts.ts` — Hook lifecycle discipline
- `/mnt/data/memoryAge.ts` — Stale memory caution
- `/mnt/data/memoryTypes.ts` — Closed memory taxonomy, Stale memory caution, Hook lifecycle discipline, Role-separated multi-agent work

## DROP candidates
- `/mnt/data/system.ts` — Only vendor- or runtime-specific patterns detected.
- `/mnt/data/systemPromptSections.ts` — Only vendor- or runtime-specific patterns detected.
- `/mnt/data/github-app.ts` — Vendor- or runtime-specific implementation detail; do not carry forward as universal behavior.
- `/mnt/data/spinnerVerbs.ts` — Vendor- or runtime-specific implementation detail; do not carry forward as universal behavior.
- `/mnt/data/turnCompletionVerbs.ts` — Vendor- or runtime-specific implementation detail; do not carry forward as universal behavior.
- `/mnt/data/errorIds.ts` — Vendor- or runtime-specific implementation detail; do not carry forward as universal behavior.
- `/mnt/data/betas.ts` — Vendor- or runtime-specific implementation detail; do not carry forward as universal behavior.
- `/mnt/data/keys.ts` — Vendor- or runtime-specific implementation detail; do not carry forward as universal behavior.
- `/mnt/data/findRelevantMemories.ts` — Only vendor- or runtime-specific patterns detected.
- `/mnt/data/oauth.ts` — Vendor- or runtime-specific implementation detail; do not carry forward as universal behavior.
- `/mnt/data/common.ts` — Vendor- or runtime-specific implementation detail; do not carry forward as universal behavior.
- `/mnt/data/product.ts` — Vendor- or runtime-specific implementation detail; do not carry forward as universal behavior.

## REVIEW set
- `/mnt/data/messages.ts` — Needs manual review.

## Operating notes
- If `.codex-hybrid/bootstrap.state.json` is missing or stale, bootstrap before non-trivial work.
- If `.codex-hybrid/profile.md` exists, read it before planning or editing.
- Keep local portable rules; drop vendor-only internals.
- On Windows, expect hookless mode even if hook files are present.
