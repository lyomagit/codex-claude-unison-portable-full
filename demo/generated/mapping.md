# Mapping

SOURCE BLOCK | ACTION | TARGET FORM | RATIONALE
--- | --- | --- | ---
`/mnt/data/prompts.ts` | PORT | Carry forward directly into Codex-native wording. | Directly portable engineering rule.; Portable change-management discipline.; Portable completion rule.; Portable reporting rule.; Portable risk policy.
`/mnt/data/system.ts` | DROP | Exclude from the hybrid contract. | Only vendor- or runtime-specific patterns detected.
`/mnt/data/systemPromptSections.ts` | DROP | Exclude from the hybrid contract. | Only vendor- or runtime-specific patterns detected.
`/mnt/data/outputStyles.ts` | ADAPT | Preserve intent but rewrite for Codex-native tools/runtime. | Interaction modes should become optional overlays, not always-on behavior.
`/mnt/data/files.ts` | PORT | Carry forward directly into Codex-native wording. | Portable filesystem safety rule.
`/mnt/data/apiLimits.ts` | ADAPT | Preserve intent but rewrite for Codex-native tools/runtime. | Portable concept, but must be remapped to Codex-native semantics.
`/mnt/data/github-app.ts` | DROP | Exclude from the hybrid contract. | Vendor- or runtime-specific implementation detail; do not carry forward as universal behavior.
`/mnt/data/xml.ts` | ADAPT | Preserve intent but rewrite for Codex-native tools/runtime. | Portable orchestration pattern; adapt to explicit Codex subagents.; Portable orchestration rule; adapt to Codex concurrency reality.
`/mnt/data/spinnerVerbs.ts` | DROP | Exclude from the hybrid contract. | Vendor- or runtime-specific implementation detail; do not carry forward as universal behavior.
`/mnt/data/turnCompletionVerbs.ts` | DROP | Exclude from the hybrid contract. | Vendor- or runtime-specific implementation detail; do not carry forward as universal behavior.
`/mnt/data/errorIds.ts` | DROP | Exclude from the hybrid contract. | Vendor- or runtime-specific implementation detail; do not carry forward as universal behavior.
`/mnt/data/betas.ts` | DROP | Exclude from the hybrid contract. | Vendor- or runtime-specific implementation detail; do not carry forward as universal behavior.
`/mnt/data/keys.ts` | DROP | Exclude from the hybrid contract. | Vendor- or runtime-specific implementation detail; do not carry forward as universal behavior.
`/mnt/data/cyberRiskInstruction.ts` | PORT | Carry forward directly into Codex-native wording. | Portable safety boundary.
`/mnt/data/messages.ts` | REVIEW | Inspect selectively before deciding. | Needs manual review.
`/mnt/data/toolLimits.ts` | ADAPT | Preserve intent but rewrite for Codex-native tools/runtime. | Portable orchestration rule; adapt to Codex concurrency reality.
`/mnt/data/tools.ts` | ADAPT | Preserve intent but rewrite for Codex-native tools/runtime. | Portable lifecycle extension pattern, but must respect Codex hook limits.; Portable orchestration pattern; adapt to explicit Codex subagents.
`/mnt/data/memdir.ts` | ADAPT | Preserve intent but rewrite for Codex-native tools/runtime. | Portable lifecycle extension pattern, but must respect Codex hook limits.
`/mnt/data/teamMemPrompts.ts` | ADAPT | Preserve intent but rewrite for Codex-native tools/runtime. | Portable lifecycle extension pattern, but must respect Codex hook limits.
`/mnt/data/memoryAge.ts` | ADAPT | Preserve intent but rewrite for Codex-native tools/runtime. | Portable and important when memory-like artifacts exist.
`/mnt/data/paths.ts` | PORT | Carry forward directly into Codex-native wording. | Portable filesystem safety rule.
`/mnt/data/memoryTypes.ts` | ADAPT | Preserve intent but rewrite for Codex-native tools/runtime. | Portable and important when memory-like artifacts exist.; Portable lifecycle extension pattern, but must respect Codex hook limits.; Portable memory design; apply when the repo uses memory-like artifacts.; Portable orchestration pattern; adapt to explicit Codex subagents.
`/mnt/data/memoryScan.ts` | PORT | Carry forward directly into Codex-native wording. | High-signal portable behavior source.
`/mnt/data/teamMemPaths.ts` | PORT | Carry forward directly into Codex-native wording. | Portable filesystem safety rule.
`/mnt/data/findRelevantMemories.ts` | DROP | Exclude from the hybrid contract. | Only vendor- or runtime-specific patterns detected.
`/mnt/data/oauth.ts` | DROP | Exclude from the hybrid contract. | Vendor- or runtime-specific implementation detail; do not carry forward as universal behavior.
`/mnt/data/common.ts` | DROP | Exclude from the hybrid contract. | Vendor- or runtime-specific implementation detail; do not carry forward as universal behavior.
`/mnt/data/product.ts` | DROP | Exclude from the hybrid contract. | Vendor- or runtime-specific implementation detail; do not carry forward as universal behavior.
