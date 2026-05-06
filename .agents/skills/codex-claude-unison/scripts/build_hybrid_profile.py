#!/usr/bin/env python3
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import os
import re
import sys
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Iterable, List, Optional, Sequence

PACKAGE_VERSION = "2026-04-28-v2.3"
MAX_READ_BYTES = 200_000
DEFAULT_MAX_FILES = 250
SKIP_DIRS = {
    ".git",
    ".hg",
    ".svn",
    ".idea",
    ".vscode",
    "node_modules",
    "vendor",
    ".venv",
    "venv",
    "dist",
    "build",
    "target",
    "coverage",
    ".next",
    ".turbo",
    ".cache",
    ".codex-hybrid/guard",
}

BINARY_EXTENSIONS = {
    ".png", ".jpg", ".jpeg", ".gif", ".bmp", ".ico", ".webp", ".tiff", ".tif",
    ".mp4", ".mov", ".avi", ".mkv", ".webm", ".wmv", ".flv", ".m4v", ".mpeg", ".mpg",
    ".mp3", ".wav", ".ogg", ".flac", ".aac", ".m4a", ".wma", ".aiff", ".opus",
    ".zip", ".tar", ".gz", ".bz2", ".7z", ".rar", ".xz", ".z", ".tgz", ".iso",
    ".exe", ".dll", ".so", ".dylib", ".bin", ".o", ".a", ".obj", ".lib", ".app",
    ".msi", ".deb", ".rpm", ".pdf", ".doc", ".docx", ".xls", ".xlsx", ".ppt",
    ".pptx", ".odt", ".ods", ".odp", ".ttf", ".otf", ".woff", ".woff2", ".eot",
    ".pyc", ".pyo", ".class", ".jar", ".war", ".ear", ".node", ".wasm", ".rlib",
    ".sqlite", ".sqlite3", ".db", ".mdb", ".idx", ".psd", ".ai", ".eps", ".sketch",
    ".fig", ".xd", ".blend", ".3ds", ".max", ".swf", ".fla", ".lockb", ".dat", ".data",
}

TEXT_HINTS = {
    ".md", ".txt", ".rst", ".adoc", ".json", ".jsonl", ".yaml", ".yml", ".toml",
    ".ts", ".tsx", ".js", ".jsx", ".py", ".rs", ".go", ".java", ".kt", ".c",
    ".cc", ".cpp", ".h", ".hpp", ".sh", ".bash", ".zsh", ".ps1", ".cmd", ".ini",
}

KNOWN_SOURCE_NAMES = {
    "prompts.ts",
    "system.ts",
    "systemPromptSections.ts",
    "outputStyles.ts",
    "files.ts",
    "apiLimits.ts",
    "tools.ts",
    "toolLimits.ts",
    "xml.ts",
    "cyberRiskInstruction.ts",
    "memdir.ts",
    "memoryTypes.ts",
    "memoryAge.ts",
    "memoryScan.ts",
    "findRelevantMemories.ts",
    "paths.ts",
    "teamMemPrompts.ts",
    "teamMemPaths.ts",
    "AGENTS.md",
    "CLAUDE.md",
    "MEMORY.md",
    "README.md",
    "HOW_TO.md",
}

CANDIDATE_DIR_NAMES = {
    ".claude",
    ".codex",
    ".agents",
    "policy",
    "policies",
    "prompt",
    "prompts",
    "docs",
    "rules",
    "memory",
    "agent",
    "agents",
}

FEATURE_RULES = [
    {
        "name": "read_before_edit",
        "label": "Read before edit",
        "action": "PORT",
        "patterns": [
            r"read before edit",
            r"read it first",
            r"read relevant files before",
            r"do not propose changes to code you haven't read",
            r"in general, do not propose changes to code you haven't read",
        ],
        "rationale": "Directly portable engineering rule.",
    },
    {
        "name": "minimal_blast_radius",
        "label": "Minimal blast radius",
        "action": "PORT",
        "patterns": [
            r"smallest correct change",
            r"minimal blast radius",
            r"avoid unrequested refactors",
            r"don't add features",
            r"don't create helpers",
            r"prefer the smallest correct change",
        ],
        "rationale": "Portable change-management discipline.",
    },
    {
        "name": "verify_before_done",
        "label": "Verify before done",
        "action": "PORT",
        "patterns": [
            r"before reporting a task complete",
            r"verify it actually works",
            r"run the test",
            r"verify changed behavior",
            r"independent verification",
        ],
        "rationale": "Portable completion rule.",
    },
    {
        "name": "truthful_reporting",
        "label": "Truthful reporting",
        "action": "PORT",
        "patterns": [
            r"report outcomes faithfully",
            r"report verified",
            r"never claim",
            r"say so explicitly",
            r"verified vs unverified",
            r"if tests fail",
        ],
        "rationale": "Portable reporting rule.",
    },
    {
        "name": "ask_before_risky",
        "label": "Ask before risky actions",
        "action": "PORT",
        "patterns": [
            r"ask before destructive",
            r"ask before risky",
            r"hard[- ]to[- ]reverse",
            r"shared state",
            r"force[- ]push",
            r"git reset --hard",
            r"shared infrastructure",
        ],
        "rationale": "Portable risk policy.",
    },
    {
        "name": "dedicated_tools",
        "label": "Prefer dedicated tools over shell",
        "action": "ADAPT",
        "patterns": [
            r"use .* instead of cat",
            r"use .* instead of sed",
            r"prefer dedicated tools",
            r"do not use the bash",
            r"instead of grep",
            r"instead of find",
        ],
        "rationale": "Portable principle, but tool names must be remapped to Codex.",
    },
    {
        "name": "parallel_safe_reads",
        "label": "Parallelize only safe independent work",
        "action": "ADAPT",
        "patterns": [
            r"parallel",
            r"concurrency[- ]safe",
            r"batch independent",
            r"multiple tools in a single response",
            r"independent tool calls",
        ],
        "rationale": "Portable orchestration rule; adapt to Codex concurrency reality.",
    },
    {
        "name": "memory_taxonomy",
        "label": "Closed memory taxonomy",
        "action": "ADAPT",
        "patterns": [
            r"user, feedback, project, and reference",
            r"types of memory",
            r"only save non-derivable",
            r"memory records can become stale",
            r"before recommending from memory",
        ],
        "rationale": "Portable memory design; apply when the repo uses memory-like artifacts.",
    },
    {
        "name": "stale_memory_caution",
        "label": "Stale memory caution",
        "action": "ADAPT",
        "patterns": [
            r"memory.*stale",
            r"verify against current code",
            r"point-in-time observations",
            r"before recommending from memory",
        ],
        "rationale": "Portable and important when memory-like artifacts exist.",
    },
    {
        "name": "output_styles",
        "label": "Explanatory or learning modes",
        "action": "ADAPT",
        "patterns": [
            r"explanatory",
            r"learning",
            r"learn by doing",
            r"educational insights",
        ],
        "rationale": "Interaction modes should become optional overlays, not always-on behavior.",
    },
    {
        "name": "path_safety",
        "label": "Path and traversal safety",
        "action": "PORT",
        "patterns": [
            r"PathTraversalError",
            r"null byte",
            r"symlink",
            r"traversal",
            r"containment",
            r"URL-encoded traversal",
        ],
        "rationale": "Portable filesystem safety rule.",
    },
    {
        "name": "binary_skip",
        "label": "Binary skip discipline",
        "action": "ADAPT",
        "patterns": [
            r"binary file extensions",
            r"isBinaryContent",
            r"can't be meaningfully compared as text",
            r"skip for text-based operations",
        ],
        "rationale": "Portable file-reading hygiene.",
    },
    {
        "name": "security_boundary",
        "label": "Security boundary",
        "action": "PORT",
        "patterns": [
            r"authorized security testing",
            r"defensive security",
            r"ctf",
            r"destructive techniques",
            r"detection evasion",
            r"supply chain compromise",
        ],
        "rationale": "Portable safety boundary.",
    },
    {
        "name": "hooks",
        "label": "Hook lifecycle discipline",
        "action": "ADAPT",
        "patterns": [
            r"hook",
            r"PreToolUse",
            r"PostToolUse",
            r"UserPromptSubmit",
            r"SessionStart",
            r"Stop",
        ],
        "rationale": "Portable lifecycle extension pattern, but must respect Codex hook limits.",
    },
    {
        "name": "subagents",
        "label": "Role-separated multi-agent work",
        "action": "ADAPT",
        "patterns": [
            r"subagent",
            r"fork",
            r"coordinator",
            r"verification agent",
            r"agent tool",
            r"worker",
        ],
        "rationale": "Portable orchestration pattern; adapt to explicit Codex subagents.",
    },
]

DROP_RULES = [
    {
        "name": "oauth_plumbing",
        "patterns": [r"oauth", r"authorize_url", r"token_url", r"client_id", r"scope"],
        "rationale": "Provider auth plumbing is not a Codex behavior rule.",
    },
    {
        "name": "provider_betas",
        "patterns": [r"beta header", r"_BETA_HEADER", r"advanced-tool-use", r"fast-mode-\d", r"context-1m-\d"],
        "rationale": "Provider feature flags are not portable harness behavior.",
    },
    {
        "name": "product_urls",
        "patterns": [r"claude\.com", r"claude\.ai", r"anthropic\.com"],
        "rationale": "Product marketing or product-identity URLs are not Codex behavior rules.",
    },
    {
        "name": "prompt_cache_internals",
        "patterns": [r"SYSTEM_PROMPT_DYNAMIC_BOUNDARY", r"cacheBreak", r"cache scope", r"prompt cache"],
        "rationale": "Prompt-cache internals are not portable instruction rules.",
    },
    {
        "name": "telemetry_ids",
        "patterns": [r"error ids", r"tracking error sources", r"billing-header", r"telemetry", r"growthbook"],
        "rationale": "Telemetry and opaque tracking identifiers are not harness behavior.",
    },
]

PORTABLE_FILENAME_HINTS = {
    "prompts.ts": "Prompt and behavior contract source.",
    "system.ts": "System prefix and environment guidance source.",
    "systemPromptSections.ts": "Prompt-section caching and dynamic/static split source.",
    "outputStyles.ts": "Optional interaction-mode source.",
    "files.ts": "Binary-skip hygiene source.",
    "apiLimits.ts": "Media and request-size constraints source.",
    "tools.ts": "Tool availability and agent-surface source.",
    "toolLimits.ts": "Tool-result budget source.",
    "xml.ts": "Message or transcript tagging conventions.",
    "cyberRiskInstruction.ts": "Security-boundary source.",
    "memdir.ts": "Memory system contract source.",
    "memoryTypes.ts": "Closed memory taxonomy source.",
    "memoryAge.ts": "Memory freshness source.",
    "memoryScan.ts": "Memory indexing and recall source.",
    "findRelevantMemories.ts": "Memory recall selection source.",
    "paths.ts": "Memory path-resolution and safety source.",
    "teamMemPrompts.ts": "Shared-vs-private memory scope source.",
    "teamMemPaths.ts": "Team-memory path-safety source.",
    "AGENTS.md": "Repo-level durable instruction source.",
    "CLAUDE.md": "Local project guidance source.",
    "HOW_TO.md": "Agent bootstrap entrypoint.",
}


@dataclass
class Match:
    name: str
    label: str
    action: str
    rationale: str


@dataclass
class FileRecord:
    path: str
    source_root: str
    size_bytes: int
    sha1: str
    text_read: bool
    action: str
    rationale: str
    matched_features: List[str] = field(default_factory=list)
    matched_drops: List[str] = field(default_factory=list)
    notes: List[str] = field(default_factory=list)


@dataclass
class ProfileSummary:
    package_version: str
    generated_at: str
    workspace: str
    archive_root: Optional[str]
    source_paths: List[str]
    file_count: int
    port_count: int
    adapt_count: int
    drop_count: int
    review_count: int
    features: List[str]


def sha1_text(content: bytes) -> str:
    return hashlib.sha1(content).hexdigest()


def is_probably_text(path: Path) -> bool:
    if path.suffix.lower() in BINARY_EXTENSIONS:
        return False
    if path.suffix.lower() in TEXT_HINTS:
        return True
    return True


def should_skip(path: Path) -> bool:
    parts = set(path.parts)
    return bool(parts & SKIP_DIRS)


def read_text_sample(path: Path) -> Optional[str]:
    try:
        raw = path.read_bytes()[:MAX_READ_BYTES]
    except Exception:
        return None
    if b"\x00" in raw:
        return None
    try:
        return raw.decode("utf-8")
    except UnicodeDecodeError:
        try:
            return raw.decode("utf-8", errors="ignore")
        except Exception:
            return None


def iter_files(sources: Sequence[Path], max_files: int) -> Iterable[tuple[Path, Path]]:
    seen = set()
    count = 0
    for source in sources:
        if not source.exists():
            continue
        if source.is_file():
            rp = source.resolve()
            if rp in seen or should_skip(rp):
                continue
            seen.add(rp)
            yield source.resolve().parent, rp
            count += 1
            if count >= max_files:
                return
            continue
        root = source.resolve()
        for path in root.rglob("*"):
            if count >= max_files:
                return
            try:
                rp = path.resolve()
            except Exception:
                continue
            if rp in seen or should_skip(rp):
                continue
            if path.is_dir():
                continue
            if not is_probably_text(path):
                continue
            seen.add(rp)
            yield root, rp
            count += 1


def detect_matches(text: str) -> tuple[List[Match], List[str]]:
    feature_matches: List[Match] = []
    drop_matches: List[str] = []
    for rule in FEATURE_RULES:
        if any(re.search(pattern, text, re.IGNORECASE) for pattern in rule["patterns"]):
            feature_matches.append(
                Match(
                    name=rule["name"],
                    label=rule["label"],
                    action=rule["action"],
                    rationale=rule["rationale"],
                )
            )
    for rule in DROP_RULES:
        if any(re.search(pattern, text, re.IGNORECASE) for pattern in rule["patterns"]):
            drop_matches.append(rule["name"])
    return feature_matches, drop_matches


def classify_file(path: Path, source_root: Path) -> FileRecord:
    try:
        raw = path.read_bytes()
    except Exception:
        raw = b""
    sample = None
    text_read = False
    if is_probably_text(path):
        sample = read_text_sample(path)
        text_read = sample is not None
    feature_matches: List[Match] = []
    drop_matches: List[str] = []
    notes: List[str] = []

    if sample:
        feature_matches, drop_matches = detect_matches(sample)

    filename_hint = PORTABLE_FILENAME_HINTS.get(path.name)
    if filename_hint:
        notes.append(filename_hint)

    action = "REVIEW"
    rationale = "Needs manual review."

    if path.name in {"oauth.ts", "betas.ts", "product.ts", "github-app.ts", "errorIds.ts", "figures.ts", "spinnerVerbs.ts", "turnCompletionVerbs.ts", "keys.ts", "common.ts"}:
        action = "DROP"
        rationale = "Vendor- or runtime-specific implementation detail; do not carry forward as universal behavior."
    elif feature_matches:
        # Strongest action wins: PORT > ADAPT.
        if any(match.action == "PORT" for match in feature_matches):
            action = "PORT"
            rationale = "; ".join(sorted({m.rationale for m in feature_matches if m.action == "PORT"}))
        else:
            action = "ADAPT"
            rationale = "; ".join(sorted({m.rationale for m in feature_matches}))
    elif drop_matches:
        action = "DROP"
        rationale = "Only vendor- or runtime-specific patterns detected."
    elif path.name in PORTABLE_FILENAME_HINTS:
        if path.name in {"outputStyles.ts", "files.ts", "apiLimits.ts", "tools.ts", "toolLimits.ts", "xml.ts"}:
            action = "ADAPT"
            rationale = "Portable concept, but must be remapped to Codex-native semantics."
        elif path.name in {"AGENTS.md", "CLAUDE.md", "HOW_TO.md", "README.md"}:
            action = "ADAPT"
            rationale = "Instructional document; preserve intent but rewrite for Codex-native behavior."
        else:
            action = "PORT"
            rationale = "High-signal portable behavior source."
    elif path.suffix.lower() in {".md", ".toml", ".yaml", ".yml", ".json"}:
        action = "REVIEW"
        rationale = "Potentially relevant configuration or documentation; inspect selectively."

    if path.name == "hooks.json" or "/hooks" in "/".join(path.parts).replace("\\", "/"):
        if action == "PORT":
            action = "ADAPT"
            rationale = "Hook lifecycle guardrail is portable, but runtime support differs by platform and event coverage."

    return FileRecord(
        path=str(path),
        source_root=str(source_root),
        size_bytes=len(raw),
        sha1=sha1_text(raw),
        text_read=text_read,
        action=action,
        rationale=rationale,
        matched_features=[m.label for m in feature_matches],
        matched_drops=drop_matches,
        notes=notes,
    )


def find_archive_root(start: Path) -> Optional[Path]:
    for candidate in [start, *start.parents]:
        if (candidate / "HOW_TO.md").exists() and (candidate / "AGENTS.md").exists():
            return candidate
    return None


def auto_discover_sources(workspace: Path, archive_root: Optional[Path]) -> List[Path]:
    candidates: List[Path] = []
    seen = set()

    def add(path: Path) -> None:
        try:
            rp = path.resolve()
        except Exception:
            return
        if not rp.exists() or rp in seen:
            return
        seen.add(rp)
        candidates.append(rp)

    add(workspace)
    if archive_root and archive_root != workspace:
        add(archive_root)

    for base in [workspace, archive_root] if archive_root else [workspace]:
        if not base or not base.exists():
            continue
        for child in base.iterdir():
            if child.name in CANDIDATE_DIR_NAMES or child.name in KNOWN_SOURCE_NAMES:
                add(child)
        for name in KNOWN_SOURCE_NAMES:
            for match in base.rglob(name):
                add(match)

    return candidates


def generate_outputs(records: List[FileRecord], workspace: Path, archive_root: Optional[Path], source_paths: List[Path], out_dir: Path) -> ProfileSummary:
    out_dir.mkdir(parents=True, exist_ok=True)
    ports = [r for r in records if r.action == "PORT"]
    adapts = [r for r in records if r.action == "ADAPT"]
    drops = [r for r in records if r.action == "DROP"]
    reviews = [r for r in records if r.action == "REVIEW"]

    feature_names = sorted({feature for r in records for feature in r.matched_features})
    summary = ProfileSummary(
        package_version=PACKAGE_VERSION,
        generated_at=dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        workspace=str(workspace),
        archive_root=str(archive_root) if archive_root else None,
        source_paths=[str(p) for p in source_paths],
        file_count=len(records),
        port_count=len(ports),
        adapt_count=len(adapts),
        drop_count=len(drops),
        review_count=len(reviews),
        features=feature_names,
    )

    inventory = {
        "summary": asdict(summary),
        "files": [asdict(r) for r in records],
    }
    (out_dir / "inventory.json").write_text(json.dumps(inventory, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    profile_lines = [
        "# Codex-Claude Unison profile",
        "",
        f"Generated: {summary.generated_at}",
        f"Package version: {summary.package_version}",
        f"Workspace: `{summary.workspace}`",
        f"Archive root: `{summary.archive_root}`" if summary.archive_root else "Archive root: not detected",
        "",
        "## Source paths",
        *[f"- `{p}`" for p in summary.source_paths],
        "",
        "## Profile summary",
        f"- Files classified: {summary.file_count}",
        f"- PORT: {summary.port_count}",
        f"- ADAPT: {summary.adapt_count}",
        f"- DROP: {summary.drop_count}",
        f"- REVIEW: {summary.review_count}",
        "",
        "## Core imported contract",
        "- Read relevant files before proposing or making changes.",
        "- Prefer the smallest correct change over speculative cleanup.",
        "- Verify changed behavior when verification is possible.",
        "- Report verified, inferred, and unverified outcomes distinctly.",
        "- Ask before destructive, public, hard-to-reverse, or shared-state actions.",
        "- Prefer dedicated tools over raw shell when tool parity exists.",
        "- Parallelize only independent, concurrency-safe work.",
        "- Treat memory as non-derivable context, not live truth.",
        "- Verify stale remembered claims against current evidence.",
        "- Behave with curiosity, ownership, and discipline; do not scope-creep.",
        "",
        "## High-signal local features detected",
    ]
    if feature_names:
        profile_lines.extend([f"- {feature}" for feature in feature_names])
    else:
        profile_lines.append("- No strong feature matches were detected; rely on the baseline hybrid contract and inspect the REVIEW set.")

    profile_lines.extend([
        "",
        "## Highest-value PORT files",
    ])
    if ports:
        for record in ports[:20]:
            detail = f" — {', '.join(record.matched_features)}" if record.matched_features else ""
            profile_lines.append(f"- `{record.path}`{detail}")
    else:
        profile_lines.append("- None detected.")

    profile_lines.extend([
        "",
        "## Highest-value ADAPT files",
    ])
    if adapts:
        for record in adapts[:25]:
            detail = f" — {', '.join(record.matched_features)}" if record.matched_features else ""
            profile_lines.append(f"- `{record.path}`{detail}")
    else:
        profile_lines.append("- None detected.")

    profile_lines.extend([
        "",
        "## DROP candidates",
    ])
    if drops:
        for record in drops[:25]:
            profile_lines.append(f"- `{record.path}` — {record.rationale}")
    else:
        profile_lines.append("- None detected.")

    profile_lines.extend([
        "",
        "## REVIEW set",
    ])
    if reviews:
        for record in reviews[:20]:
            profile_lines.append(f"- `{record.path}` — {record.rationale}")
    else:
        profile_lines.append("- None detected.")

    profile_lines.extend([
        "",
        "## Operating notes",
        "- If `.codex-hybrid/bootstrap.state.json` is missing or stale, bootstrap before non-trivial work.",
        "- If `.codex-hybrid/profile.md` exists, read it before planning or editing.",
        "- Keep local portable rules; drop vendor-only internals.",
        "- On Windows, expect hookless mode even if hook files are present.",
    ])

    (out_dir / "profile.md").write_text("\n".join(profile_lines) + "\n", encoding="utf-8")

    mapping_lines = [
        "# Mapping",
        "",
        "SOURCE BLOCK | ACTION | TARGET FORM | RATIONALE",
        "--- | --- | --- | ---",
    ]
    for record in records:
        target_form = {
            "PORT": "Carry forward directly into Codex-native wording.",
            "ADAPT": "Preserve intent but rewrite for Codex-native tools/runtime.",
            "DROP": "Exclude from the hybrid contract.",
            "REVIEW": "Inspect selectively before deciding.",
        }[record.action]
        mapping_lines.append(
            f"`{record.path}` | {record.action} | {target_form} | {record.rationale}"
        )
    (out_dir / "mapping.md").write_text("\n".join(mapping_lines) + "\n", encoding="utf-8")

    return summary


def parse_args(argv: Sequence[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build a local Codex-Claude Unison hybrid profile.")
    parser.add_argument("--source", action="append", default=[], help="Source file or directory to ingest. May be specified multiple times.")
    parser.add_argument("--workspace", default=os.getcwd(), help="Workspace path used for auto-discovery and reporting.")
    parser.add_argument("--archive-root", default=None, help="Archive root for package-relative auto-discovery.")
    parser.add_argument("--out", required=True, help="Output directory for generated profile, mapping, and inventory.")
    parser.add_argument("--max-files", type=int, default=DEFAULT_MAX_FILES, help="Maximum number of files to classify.")
    return parser.parse_args(argv)


def main(argv: Sequence[str]) -> int:
    args = parse_args(argv)
    workspace = Path(args.workspace).resolve()
    archive_root = Path(args.archive_root).resolve() if args.archive_root else find_archive_root(Path(__file__).resolve())
    explicit_sources = [Path(p).resolve() for p in args.source]
    source_paths = explicit_sources or auto_discover_sources(workspace, archive_root)
    records = [classify_file(path, source_root) for source_root, path in iter_files(source_paths, args.max_files)]
    summary = generate_outputs(records, workspace, archive_root, source_paths, Path(args.out).resolve())
    print(json.dumps(asdict(summary), indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
