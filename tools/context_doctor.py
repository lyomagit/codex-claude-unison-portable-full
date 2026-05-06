#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

LARGE_FILE_BYTES = 200_000
STALE_DAYS = 7
MAX_SCAN_FILES = 5000


@dataclass
class Finding:
    severity: str
    category: str
    path: str
    message: str
    estimated_savings_bytes: int = 0
    action: str = "review"


def human_bytes(n: int) -> str:
    units = ["B", "KB", "MB", "GB"]
    value = float(max(0, n))
    for unit in units:
        if value < 1024 or unit == units[-1]:
            return f"{value:.1f} {unit}" if unit != "B" else f"{int(value)} B"
        value /= 1024
    return f"{int(n)} B"


def file_age_days(path: Path) -> Optional[int]:
    try:
        return max(0, int((datetime.now(timezone.utc).timestamp() - path.stat().st_mtime) // 86400))
    except Exception:
        return None


def safe_size(path: Path) -> Optional[int]:
    try:
        return path.stat().st_size
    except Exception:
        return None


def iter_files(root: Path) -> Iterable[Path]:
    count = 0
    skip_dirs = {".git", "node_modules", "__pycache__", ".venv", "venv", "dist", "build"}
    for base, dirs, files in os.walk(root):
        dirs[:] = [d for d in dirs if d not in skip_dirs]
        for name in files:
            count += 1
            if count > MAX_SCAN_FILES:
                return
            yield Path(base) / name


def inspect_tool_results(root: Path, findings: List[Finding]) -> None:
    tr = root / ".codex-hybrid" / "tool-results"
    if not tr.exists():
        return
    total = 0
    for path in tr.glob("*"):
        if not path.is_file() or path.suffix == ".json":
            continue
        size = safe_size(path) or 0
        total += size
        if size >= LARGE_FILE_BYTES:
            findings.append(Finding(
                "info", "persisted-tool-result", str(path),
                f"Large output is already disk-backed ({human_bytes(size)}). Keep only the preview in chat and reopen this path when needed.",
                max(0, size - 4096), "keep-on-disk",
            ))
    if total >= LARGE_FILE_BYTES:
        findings.append(Finding(
            "info", "tool-result-store", str(tr),
            f"Tool-result store totals {human_bytes(total)}. This is good context hygiene if those bytes were kept out of the conversation.",
            max(0, total - 4096), "reference-paths-not-full-output",
        ))


def inspect_generated_profiles(root: Path, findings: List[Finding]) -> None:
    hybrid = root / ".codex-hybrid"
    for name in ("profile.md", "mapping.md", "inventory.json"):
        path = hybrid / name
        if not path.exists():
            continue
        size = safe_size(path) or 0
        age = file_age_days(path)
        if age is not None and age > STALE_DAYS:
            findings.append(Finding(
                "warn", "stale-generated-profile", str(path),
                f"Generated hybrid artifact is {age} days old. Refresh before relying on it for current code state.",
                0, "rerun build_hybrid_profile.py",
            ))
        if size > LARGE_FILE_BYTES:
            findings.append(Finding(
                "warn", "bulky-generated-profile", str(path),
                f"Generated artifact is large ({human_bytes(size)}). Prefer targeted reads over loading the whole file repeatedly.",
                max(0, size - 50_000), "read selectively or regenerate leaner",
            ))


def inspect_unresolved_guard_state(root: Path, findings: List[Finding]) -> None:
    path = root / ".codex-hybrid" / "guard" / "unison_turn_state.v2.json"
    if not path.exists():
        return
    try:
        state = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        findings.append(Finding("warn", "guard-state", str(path), "Guard state is unreadable JSON.", 0, "inspect manually"))
        return
    last_failure = state.get("last_failure_index")
    last_success = state.get("last_successful_verification_index")
    unresolved = last_failure is not None and (last_success is None or int(last_success) < int(last_failure))
    if unresolved:
        findings.append(Finding(
            "blocker", "unresolved-shell-failure", str(path),
            "A real non-zero command failure appears unresolved. Do not claim success until it is fixed and re-verified or reported plainly.",
            0, "rerun/fix/report failing verification",
        ))


def inspect_large_context_candidates(root: Path, findings: List[Finding]) -> None:
    text_suffixes = {".md", ".txt", ".log", ".json", ".jsonl", ".yaml", ".yml", ".toml", ".out"}
    for path in iter_files(root):
        try:
            rel = path.relative_to(root)
        except Exception:
            rel = path
        rel_s = str(rel).replace("\\", "/")
        if rel_s.startswith(".git/") or rel_s.startswith(".codex-hybrid/tool-results/"):
            continue
        if path.suffix.lower() not in text_suffixes:
            continue
        size = safe_size(path) or 0
        if size >= LARGE_FILE_BYTES:
            category = "large-log-or-artifact" if path.suffix.lower() in {".log", ".out", ".jsonl"} else "large-text-artifact"
            findings.append(Finding(
                "warn", category, str(path),
                f"Large text artifact ({human_bytes(size)}) can bloat context if pasted or read wholesale.",
                max(0, size - 20_000), "summarize, persist, or read ranges only",
            ))


def build_report(root: Path) -> Dict[str, Any]:
    root = root.resolve()
    findings: List[Finding] = []
    inspect_tool_results(root, findings)
    inspect_generated_profiles(root, findings)
    inspect_unresolved_guard_state(root, findings)
    inspect_large_context_candidates(root, findings)
    total_savings = sum(f.estimated_savings_bytes for f in findings)
    return {
        "schema": "codex-claude-unison.context-doctor.v1",
        "root": str(root),
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "finding_count": len(findings),
        "estimated_savings_bytes": total_savings,
        "findings": [asdict(f) for f in findings],
    }


def render_markdown(report: Dict[str, Any]) -> str:
    lines = ["# Context doctor", "", f"Root: `{report['root']}`", f"Findings: {report['finding_count']}", f"Estimated avoidable context: {human_bytes(int(report['estimated_savings_bytes']))}", ""]
    if not report["findings"]:
        lines.append("No obvious context bloat sources found. This does not prove the active chat context is small; it only audits local files and guard state.")
        return "\n".join(lines) + "\n"
    for item in report["findings"]:
        lines.extend([
            f"## {item['severity'].upper()} — {item['category']}",
            f"Path: `{item['path']}`",
            item["message"],
            f"Suggested action: {item['action']}",
            f"Estimated savings: {human_bytes(int(item.get('estimated_savings_bytes') or 0))}",
            "",
        ])
    lines.append("No files were modified or deleted.")
    return "\n".join(lines) + "\n"


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Offline context-health audit for the Codex-Claude Unison bundle.")
    parser.add_argument("--root", default=os.getcwd(), help="Workspace root to audit.")
    parser.add_argument("--json", action="store_true", help="Print JSON instead of markdown.")
    return parser.parse_args(argv)


def main(argv: list[str]) -> int:
    args = parse_args(argv)
    report = build_report(Path(args.root))
    if args.json:
        print(json.dumps(report, indent=2, ensure_ascii=False))
    else:
        print(render_markdown(report))
    return 0


if __name__ == "__main__":
    import sys
    raise SystemExit(main(sys.argv[1:]))
