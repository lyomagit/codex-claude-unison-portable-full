#!/usr/bin/env python3
from __future__ import annotations

import argparse
import datetime as dt
import fnmatch
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

PACKAGE_NAME = "codex-claude-unison"
PACKAGE_VERSION = "2026-05-09-v3.1"
MANAGED_START = "<!-- codex-claude-unison:start -->"
MANAGED_END = "<!-- codex-claude-unison:end -->"

LEGACY_ALIASES = [
    "codex-claude-unison",
    "codex-claude-hybrid",
    "codex-claude-unison-hooks",
    "codex-claude-unison-portable",
    "codex-claude-unison-portable-full",
]
LEGACY_AGENT_PATTERNS = ["hybrid-*.toml", "codex-claude-hybrid*.toml", "codex-claude-unison*.toml"]
ROOT_DOCS_TO_COPY = [
    "README.md",
    "HOW_TO.md",
    "HYBRID_MODEL_INSTRUCTIONS.md",
    "ONE_ARCHIVE_MANIFEST.json",
    "HOOKS_V3_AUDIT.md",
    "MIGRATION_NOTES.md",
    "PRODUCTION_READINESS.md",
]
ROOT_DOC_MANAGED_SUFFIXES = {
    "README.md": "README.codex-claude-unison.md",
    "HOW_TO.md": "HOW_TO.codex-claude-unison.md",
    "HYBRID_MODEL_INSTRUCTIONS.md": "HYBRID_MODEL_INSTRUCTIONS.codex-claude-unison.md",
}
LEGACY_ROOT_DOC_NAMES = [
    "HOW_TO.codex-claude-unison.md",
    "README.codex-claude-unison.md",
    "HYBRID_MODEL_INSTRUCTIONS.codex-claude-unison.md",
    "HOW_TO.codex-claude-hybrid.md",
    "README.codex-claude-hybrid.md",
    "HYBRID_MODEL_INSTRUCTIONS.codex-claude-hybrid.md",
]
DOC_FILES_TO_COPY = [
    "docs/context-hygiene.md",
    "docs/plan-handoff-template.md",
    "docs/retry-policy.md",
]
TOOL_FILES_TO_COPY = [
    "tools/persist_tool_result.py",
    "tools/context_doctor.py",
    "tools/verify_bundle.py",
    "tools/tests/run_tool_fixtures.py",
    "tools/tests/run_installer_fixtures.py",
]
CUSTOM_AGENTS = [
    "unison-mapper.toml",
    "unison-reviewer.toml",
    "unison-implementer.toml",
    "unison-verifier.toml",
]
HOOK_SCRIPT_FILES = [
    "common.py",
    "context_hook.py",
    "pre_tool_use_guard.py",
    "post_tool_use_guard.py",
    "stop_turn_guard.py",
]
LEGACY_HOOK_FILES = [
    "pre_tool_use_policy.py",
    "post_tool_use_review.py",
    "stop_enforcer.py",
    "post_tool_use_guard.py.disabled-by-codex-claude-unison-v2",
    "pre_tool_use_policy.py.disabled-by-codex-claude-unison-v2",
    "post_tool_use_review.py.disabled-by-codex-claude-unison-v2",
    "stop_enforcer.py.disabled-by-codex-claude-unison-v2",
]
ALL_KNOWN_HOOK_NAMES = HOOK_SCRIPT_FILES + LEGACY_HOOK_FILES
INSTALL_WRAPPERS = ["install.sh", "install.ps1", "install.cmd"]


def parse_args(argv: Sequence[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Portable bootstrap for the Codex-Claude Unison replacement bundle.")
    parser.add_argument("--mode", choices=["auto", "repo", "global", "both"], default="auto")
    parser.add_argument("--target", default=os.getcwd(), help="Target path used to detect the repository/workspace root or global install context.")
    parser.add_argument("--source", action="append", default=[], help="Optional source file or directory for the profile builder. May be specified multiple times.")
    parser.add_argument("--skip-hooks", action="store_true", help="Do not install hooks or enable the codex_hooks feature flag.")
    parser.add_argument("--replace-existing", action="store_true", help="Backup and replace old managed Codex-Claude Unison/hybrid installs.")
    parser.add_argument("--backup-dir", default=None, help="Override backup directory. Defaults to .codex-hybrid/backups/... for repo installs or ~/.codex/backups/... for global installs.")
    parser.add_argument("--dry-run", action="store_true", help="Report planned changes without modifying files.")
    parser.add_argument("--yes", action="store_true", help="Accepted for compatibility; bootstrap is non-interactive.")
    parser.add_argument("--json", action="store_true", help="Print machine-readable JSON summary.")
    return parser.parse_args(argv)


def find_archive_root(start: Path) -> Path:
    for candidate in [start, *start.parents]:
        if (
            (candidate / "HOW_TO.md").exists()
            and (candidate / "AGENTS.md").exists()
            and (candidate / ".agents" / "skills" / PACKAGE_NAME / "SKILL.md").exists()
        ):
            return candidate
    raise SystemExit("Could not determine archive root.")


def find_git_root(start: Path) -> Optional[Path]:
    try:
        start = start.resolve()
    except Exception:
        start = Path.cwd()
    if start.is_file():
        start = start.parent
    for candidate in [start, *start.parents]:
        if (candidate / ".git").exists():
            return candidate
    return None


def workspace_root(target: Path) -> Path:
    return find_git_root(target) or target.resolve()


def codex_home() -> Path:
    return Path.home() / ".codex"


def personal_skills_home() -> Path:
    return Path.home() / ".agents" / "skills"


def ensure_dir(path: Path, *, dry_run: bool = False) -> Path:
    if not dry_run:
        path.mkdir(parents=True, exist_ok=True)
    return path


def read_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8") if path.exists() else ""
    except UnicodeDecodeError:
        return ""


def write_text_raw(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def hash_path(path: Path) -> Tuple[int, str]:
    if path.is_file():
        return path.stat().st_size, sha256_file(path)
    h = hashlib.sha256()
    total = 0
    if path.is_dir():
        for item in sorted(p for p in path.rglob("*") if p.is_file()):
            rel = item.relative_to(path).as_posix()
            item_hash = sha256_file(item)
            total += item.stat().st_size
            h.update(rel.encode("utf-8", "surrogatepass"))
            h.update(b"\0")
            h.update(item_hash.encode("ascii"))
            h.update(b"\0")
    return total, h.hexdigest()


def same_file_content(src: Path, dst: Path) -> bool:
    if not src.exists() or not dst.exists() or not src.is_file() or not dst.is_file():
        return False
    try:
        return src.stat().st_size == dst.stat().st_size and sha256_file(src) == sha256_file(dst)
    except Exception:
        return False


def is_managed_text(text: str) -> bool:
    lowered = text.lower()
    return any(alias in lowered for alias in LEGACY_ALIASES) or "codex-claude unison" in lowered or "codex-claude hybrid" in lowered


def is_managed_file(path: Path) -> bool:
    if not path.exists():
        return False
    if path.name in ALL_KNOWN_HOOK_NAMES:
        return True
    if path.name in LEGACY_ROOT_DOC_NAMES:
        return True
    text = read_text(path)
    return bool(text and is_managed_text(text))


def safe_relative(path: Path, base: Path) -> str:
    try:
        return path.resolve().relative_to(base.resolve()).as_posix()
    except Exception:
        safe = re.sub(r"[^A-Za-z0-9._-]+", "_", str(path.resolve()))
        return safe.strip("_") or path.name


class ChangeRecorder:
    def __init__(self, *, dry_run: bool, replace_existing: bool, backup_root: Optional[Path], base_root: Path) -> None:
        self.dry_run = dry_run
        self.replace_existing = replace_existing
        self.backup_root = backup_root
        self.base_root = base_root
        self.files_copied: List[str] = []
        self.files_replaced: List[str] = []
        self.files_removed: List[str] = []
        self.files_skipped: List[str] = []
        self.config_edits: List[str] = []
        self.warnings: List[str] = []
        self.backup_manifest: Dict[str, Any] = {
            "package_name": PACKAGE_NAME,
            "package_version": PACKAGE_VERSION,
            "generated_at": dt.datetime.now(dt.timezone.utc).isoformat(),
            "dry_run": dry_run,
            "entries": [],
        }

    def backup_path_for(self, path: Path) -> Path:
        if self.backup_root is None:
            raise RuntimeError("backup root not configured")
        return self.backup_root / safe_relative(path, self.base_root)

    def backup(self, path: Path, action: str) -> None:
        if not path.exists() or self.backup_root is None:
            return
        size, digest = hash_path(path)
        dst = self.backup_path_for(path)
        entry = {
            "original_path": str(path),
            "backup_path": str(dst),
            "file_size": size,
            "sha256": digest,
            "is_directory": path.is_dir(),
            "action_planned": action,
        }
        self.backup_manifest["entries"].append(entry)
        if self.dry_run:
            return
        if path.is_dir():
            if dst.exists():
                suffix = 1
                base = dst
                while dst.exists():
                    dst = Path(str(base) + f".{suffix}")
                    suffix += 1
                entry["backup_path"] = str(dst)
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copytree(path, dst, ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
        else:
            dst.parent.mkdir(parents=True, exist_ok=True)
            if dst.exists():
                suffix = 1
                base = dst
                while dst.exists():
                    dst = Path(str(base) + f".{suffix}")
                    suffix += 1
                entry["backup_path"] = str(dst)
            shutil.copy2(path, dst)

    def finalize_backup_manifest(self) -> Optional[str]:
        if self.backup_root is None or not self.backup_manifest["entries"]:
            return None
        manifest_path = self.backup_root / "backup_manifest.json"
        if not self.dry_run:
            manifest_path.parent.mkdir(parents=True, exist_ok=True)
            manifest_path.write_text(json.dumps(self.backup_manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        return str(manifest_path)

    def copy_file(self, src: Path, dst: Path) -> None:
        if not src.exists():
            self.warnings.append(f"missing source file: {src}")
            return
        if src.resolve() == dst.resolve():
            self.files_skipped.append(str(dst))
            return
        if dst.exists() and same_file_content(src, dst):
            self.files_skipped.append(str(dst))
            return
        if dst.exists():
            if not self.replace_existing and not is_managed_file(dst):
                self.warnings.append(f"skipped existing unmanaged file without --replace-existing: {dst}")
                self.files_skipped.append(str(dst))
                return
            self.backup(dst, "replace_file")
            self.files_replaced.append(str(dst))
        else:
            self.files_copied.append(str(dst))
        if not self.dry_run:
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dst)

    def write_text(self, dst: Path, content: str, *, reason: str = "write_text") -> None:
        old = read_text(dst)
        if dst.exists() and old == content:
            self.files_skipped.append(str(dst))
            return
        if dst.exists():
            self.backup(dst, reason)
            self.files_replaced.append(str(dst))
        else:
            self.files_copied.append(str(dst))
        if not self.dry_run:
            write_text_raw(dst, content)

    def copy_tree(self, src: Path, dst: Path) -> None:
        if not src.exists():
            self.warnings.append(f"missing source directory: {src}")
            return
        if src.resolve() == dst.resolve():
            self.files_skipped.append(str(dst))
            return
        if dst.exists():
            if not self.replace_existing and not path_is_managed_tree(dst):
                self.warnings.append(f"skipped existing directory without --replace-existing: {dst}")
                self.files_skipped.append(str(dst))
                return
            self.backup(dst, "replace_directory")
            self.files_replaced.append(str(dst))
        else:
            self.files_copied.append(str(dst))
        if not self.dry_run:
            if dst.exists():
                shutil.rmtree(dst)
            shutil.copytree(src, dst, ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))

    def remove_path(self, path: Path, *, reason: str = "remove_managed_path") -> None:
        if not path.exists():
            return
        self.backup(path, reason)
        self.files_removed.append(str(path))
        if not self.dry_run:
            if path.is_dir():
                shutil.rmtree(path)
            else:
                path.unlink()


def path_is_managed_tree(path: Path) -> bool:
    if path.name in LEGACY_ALIASES:
        return True
    marker_files = ["SKILL.md", "bootstrap.state.json", "README.md", "HOW_TO.md"]
    for name in marker_files:
        candidate = path / name
        if candidate.exists() and is_managed_file(candidate):
            return True
    # Hook and custom-agent directories can be package managed by exact file names.
    if any((path / name).exists() for name in ALL_KNOWN_HOOK_NAMES):
        return True
    return False


def make_backup_root(default_parent: Path, override: Optional[str], *, dry_run: bool) -> Path:
    if override:
        root = Path(override).expanduser().resolve()
    else:
        stamp = dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        root = default_parent / f"{stamp}-pre-v3.1"
    if not dry_run:
        candidate = root
        suffix = 1
        while candidate.exists():
            candidate = Path(str(root) + f"-{suffix}")
            suffix += 1
        candidate.mkdir(parents=True, exist_ok=False)
        return candidate
    return root


def managed_agents_block(how_to_filename: str) -> str:
    return "\n".join([
        MANAGED_START,
        "## Codex-Claude Unison",
        "",
        f"- If `{how_to_filename}` exists and `.codex-hybrid/bootstrap.state.json` is missing or stale, self-bootstrap this bundle before non-trivial work.",
        "- If `.codex-hybrid/profile.md` exists, read it before planning, editing, or reporting.",
        "- Behave with curiosity, ownership, and discipline. Help the project like a careful engineering partner, not a passive autocomplete.",
        "- Read before edit, prefer the smallest correct change, verify when possible, and report results truthfully.",
        "- Treat any real non-zero shell exit in the current turn as unresolved until it is fixed and re-verified or reported plainly.",
        "- Do not infer shell failure from scary words in stdout/stderr. Trust structured exit_code first, then transcript exec_command_end by tool_use_id.",
        "- Ask before destructive, public, hard-to-reverse, shared-infrastructure, secret-exposure, network-upload, or background/subagent-risk actions. Name the concrete reason and provenance.",
        "- Persist very large outputs with tools/persist_tool_result.py; use tools/context_doctor.py when context is bloated.",
        "- Compaction is lossy. Preserve operational state: current request, modified/read files, commands and outcomes, unresolved failures, plan/task state, verification state, active processes/ports, persisted result paths, durable decisions, and the next concrete step.",
        MANAGED_END,
        "",
    ])


def managed_global_block() -> str:
    return "\n".join([
        MANAGED_START,
        "# Codex-Claude Unison global defaults",
        "",
        "- Use the personal `codex-claude-unison` skill when this replacement bundle is relevant.",
        "- If the current repository has `.codex-hybrid/profile.md`, read it before planning or editing.",
        "- Behave with curiosity, stewardship, truthful verification, and bounded scope.",
        "- Ask before destructive, public, hard-to-reverse, shared-state, secret-exposure, network-upload, or background-risk actions with a concrete reason.",
        "- For shell failures, trust exit_code/transcript evidence, not scary stdout/stderr words.",
        MANAGED_END,
        "",
    ])


def remove_all_managed_blocks(text: str) -> Tuple[str, int]:
    count = 0
    aliases = [re.escape(alias) for alias in LEGACY_ALIASES]
    # Exact marker pairs first.
    marker_pairs = [(MANAGED_START, MANAGED_END)]
    for alias in LEGACY_ALIASES:
        marker_pairs.extend([
            (f"<!-- {alias}:start -->", f"<!-- {alias}:end -->"),
            (f"<!-- {alias}: begin -->", f"<!-- {alias}: end -->"),
        ])
    for start, end in marker_pairs:
        while start in text and end in text:
            before, _, rest = text.partition(start)
            _, _, after = rest.partition(end)
            text = before.rstrip() + "\n\n" + after.lstrip("\n")
            count += 1
    # Broad fallback for old managed comments.
    pattern = re.compile(r"<!--\s*(?:" + "|".join(aliases) + r")[^>]*start\s*-->.*?<!--\s*(?:" + "|".join(aliases) + r")[^>]*end\s*-->", re.IGNORECASE | re.DOTALL)
    text, n = pattern.subn("", text)
    count += n
    return text.strip() + ("\n" if text.strip() else ""), count


def merge_agents_file(target_path: Path, package_agents_path: Path, how_to_filename: str, recorder: ChangeRecorder) -> Dict[str, Any]:
    original = read_text(target_path)
    if not target_path.exists():
        recorder.copy_file(package_agents_path, target_path)
        return {"path": str(target_path), "mode": "created_from_package"}
    cleaned, removed = remove_all_managed_blocks(original)
    block = managed_agents_block(how_to_filename)
    new_text = cleaned.rstrip() + "\n\n" + block if cleaned.strip() else block
    recorder.write_text(target_path, new_text, reason="merge_agents_managed_block")
    return {"path": str(target_path), "mode": "merged", "managed_blocks_removed": removed}


def merge_global_override(target_path: Path, recorder: ChangeRecorder) -> Dict[str, Any]:
    original = read_text(target_path)
    cleaned, removed = remove_all_managed_blocks(original)
    block = managed_global_block()
    new_text = cleaned.rstrip() + "\n\n" + block if cleaned.strip() else block
    recorder.write_text(target_path, new_text, reason="merge_global_override")
    return {"path": str(target_path), "managed_blocks_removed": removed}


def _table_header_re(table: str) -> str:
    return r"^\s*\[" + re.escape(table) + r"\]\s*(?:#.*)?$"


def _key_line_re(key: str) -> str:
    return r"^\s*" + re.escape(key) + r"\s*="


def _section_bounds(lines: List[str], table: str) -> Optional[Tuple[int, int]]:
    header_re = re.compile(_table_header_re(table))
    start: Optional[int] = None
    for idx, line in enumerate(lines):
        if header_re.match(line):
            start = idx
            break
    if start is None:
        return None
    end = len(lines)
    table_re = re.compile(r"^\s*\[.*\]\s*(?:#.*)?$")
    for idx in range(start + 1, len(lines)):
        if table_re.match(lines[idx]):
            end = idx
            break
    return start, end


def _strip_inline_comment(value: str) -> str:
    in_single = False
    in_double = False
    escaped = False
    out: List[str] = []
    for ch in value:
        if escaped:
            out.append(ch)
            escaped = False
            continue
        if ch == "\\" and in_double:
            out.append(ch)
            escaped = True
            continue
        if ch == "'" and not in_double:
            in_single = not in_single
            out.append(ch)
            continue
        if ch == '"' and not in_single:
            in_double = not in_double
            out.append(ch)
            continue
        if ch == "#" and not in_single and not in_double:
            break
        out.append(ch)
    return "".join(out).strip()


def _get_table_bool(toml_text: str, table: str, key: str) -> Optional[bool]:
    lines = toml_text.splitlines()
    bounds = _section_bounds(lines, table)
    if bounds is None:
        return None
    start, end = bounds
    key_re = re.compile(_key_line_re(key))
    for line in lines[start + 1 : end]:
        if not key_re.match(line):
            continue
        _, value = line.split("=", 1)
        normalized = _strip_inline_comment(value).lower()
        if normalized == "true":
            return True
        if normalized == "false":
            return False
    return None


def _upsert_key_in_table(toml_text: str, table: str, key: str, value: str) -> Tuple[str, bool]:
    lines = toml_text.splitlines()
    key_line = f"{key} = {value}"
    bounds = _section_bounds(lines, table)
    if bounds is None:
        suffix = "\n" if toml_text and not toml_text.endswith("\n") else ""
        return toml_text + suffix + f"\n[{table}]\n{key_line}\n", True
    start, end = bounds
    key_re = re.compile(_key_line_re(key))
    for idx in range(start + 1, end):
        if key_re.match(lines[idx]):
            indent = lines[idx][: len(lines[idx]) - len(lines[idx].lstrip())]
            old = lines[idx]
            lines[idx] = indent + key_line
            return "\n".join(lines) + ("\n" if toml_text.endswith("\n") or not toml_text else ""), old != lines[idx]
    lines.insert(end, key_line)
    return "\n".join(lines) + ("\n" if toml_text.endswith("\n") or not toml_text else ""), True


def _remove_keys_from_table(toml_text: str, table: str, keys: Iterable[str]) -> Tuple[str, List[str]]:
    lines = toml_text.splitlines()
    bounds = _section_bounds(lines, table)
    if bounds is None:
        return toml_text, []
    start, end = bounds
    key_res = [(key, re.compile(_key_line_re(key))) for key in keys]
    removed: List[str] = []
    new_lines: List[str] = []
    for idx, line in enumerate(lines):
        hit = None
        if start < idx < end:
            for key, rx in key_res:
                if rx.match(line):
                    hit = key
                    break
        if hit:
            removed.append(hit)
            continue
        new_lines.append(line)
    return "\n".join(new_lines) + ("\n" if toml_text.endswith("\n") or not toml_text else ""), removed


def _remove_empty_table(toml_text: str, table: str) -> Tuple[str, bool]:
    lines = toml_text.splitlines()
    bounds = _section_bounds(lines, table)
    if bounds is None:
        return toml_text, False
    start, end = bounds
    body = lines[start + 1 : end]
    has_real_content = any(line.strip() and not line.strip().startswith("#") for line in body)
    if has_real_content:
        return toml_text, False
    kept = lines[:start] + lines[end:]
    return "\n".join(kept).strip() + ("\n" if kept else ""), True


def normalize_multi_agent_v2_conflicts(toml_text: str) -> Tuple[str, List[str]]:
    edits: List[str] = []
    if _get_table_bool(toml_text, "features", "multi_agent_v2") is not True:
        return toml_text, edits
    toml_text, removed = _remove_keys_from_table(toml_text, "agents", ("max_threads", "max_depth"))
    if removed:
        edits.append("removed incompatible [agents]." + ",".join(removed) + " because multi_agent_v2=true")
    toml_text, removed_empty = _remove_empty_table(toml_text, "agents")
    if removed_empty:
        edits.append("removed empty [agents] section")
    return toml_text, edits


def codex_config_new_text(old_text: str, enable_hooks: bool) -> Tuple[str, List[str]]:
    edits: List[str] = []
    text, e = normalize_multi_agent_v2_conflicts(old_text)
    edits.extend(e)
    if enable_hooks:
        text, changed = _upsert_key_in_table(text, "features", "codex_hooks", "true")
        if changed:
            edits.append("set [features].codex_hooks = true")
    text, e = normalize_multi_agent_v2_conflicts(text)
    edits.extend(e)
    if text and not text.endswith("\n"):
        text += "\n"
    return text, edits


def ensure_codex_config(config_path: Path, enable_hooks: bool) -> Path:
    text, _ = codex_config_new_text(read_text(config_path), enable_hooks)
    write_text_raw(config_path, text)
    return config_path


def update_codex_config(config_path: Path, enable_hooks: bool, recorder: ChangeRecorder) -> Dict[str, Any]:
    old = read_text(config_path)
    new, edits = codex_config_new_text(old, enable_hooks)
    recorder.write_text(config_path, new, reason="update_codex_config")
    recorder.config_edits.extend(edits)
    return {"path": str(config_path), "edits": edits}


def script_command(script_path: Path) -> str:
    return subprocess.list2cmdline([str(Path(sys.executable).resolve()), str(script_path.resolve())])


def hooks_payload(hooks_dir: Path) -> Dict[str, Any]:
    def hook(script: str, status: str, timeout: int = 30) -> Dict[str, Any]:
        return {
            "type": "command",
            "command": script_command(hooks_dir / script),
            "timeout": timeout,
            "statusMessage": status,
        }

    return {
        "hooks": {
            "SessionStart": [{"matcher": "startup|resume|clear", "hooks": [hook("context_hook.py", "Loading hybrid context")]}],
            "UserPromptSubmit": [{"hooks": [hook("context_hook.py", "Applying hybrid context")]}],
            "PreToolUse": [{"matcher": "^(Bash|bash|Shell|shell|sh|PowerShell|powershell|pwsh|cmd|terminal|exec|unified_exec)$", "hooks": [hook("pre_tool_use_guard.py", "Checking shell command")]}],
            "PostToolUse": [{"matcher": "^(Bash|bash|Shell|shell|sh|PowerShell|powershell|pwsh|cmd|terminal|exec|unified_exec)$", "hooks": [hook("post_tool_use_guard.py", "Reviewing shell output")]}],
            "Stop": [{"hooks": [hook("stop_turn_guard.py", "Checking completion claims")]}],
        }
    }


def command_mentions_known_unison_hook(command: Any, hooks_dir: Optional[Path] = None) -> bool:
    if not isinstance(command, str):
        return False
    normalized = command.replace("\\", "/").lower()
    if any(alias in normalized for alias in LEGACY_ALIASES):
        return True
    hook_names = [name.lower().split(".disabled")[0] for name in ALL_KNOWN_HOOK_NAMES]
    if hooks_dir is not None:
        try:
            hooks_norm = hooks_dir.resolve().as_posix().lower()
        except Exception:
            hooks_norm = str(hooks_dir).replace("\\", "/").lower()
        if hooks_norm in normalized and any(name in normalized for name in hook_names):
            return True
    if ("/.codex/hooks/" in normalized or ".codex/hooks/" in normalized) and any(name in normalized for name in hook_names):
        return True
    return False


def prune_unison_hook_duplicates(hooks_json: Dict[str, Any], hooks_dir: Optional[Path] = None) -> Tuple[Dict[str, Any], int]:
    hooks = hooks_json.get("hooks")
    if not isinstance(hooks, dict):
        return hooks_json, 0
    removed = 0
    for event_name in list(hooks.keys()):
        groups = hooks.get(event_name)
        if not isinstance(groups, list):
            continue
        kept_groups = []
        for group in groups:
            if not isinstance(group, dict):
                kept_groups.append(group)
                continue
            handlers = group.get("hooks")
            if not isinstance(handlers, list):
                kept_groups.append(group)
                continue
            kept_handlers = []
            for handler in handlers:
                if isinstance(handler, dict) and command_mentions_known_unison_hook(handler.get("command"), hooks_dir):
                    removed += 1
                    continue
                kept_handlers.append(handler)
            if kept_handlers:
                new_group = dict(group)
                new_group["hooks"] = kept_handlers
                kept_groups.append(new_group)
        if kept_groups:
            hooks[event_name] = kept_groups
        else:
            hooks.pop(event_name, None)
    return hooks_json, removed


def merge_hooks_json(target_hooks_path: Path, hooks_dir: Path, recorder: ChangeRecorder) -> Dict[str, Any]:
    package_data = hooks_payload(hooks_dir)
    removed = 0
    if target_hooks_path.exists():
        try:
            target_data = json.loads(read_text(target_hooks_path))
            if not isinstance(target_data, dict):
                raise ValueError("hooks.json root must be an object")
        except Exception:
            target_data = {}
            recorder.warnings.append(f"invalid hooks.json replaced after backup: {target_hooks_path}")
    else:
        target_data = {}
    target_data, removed = prune_unison_hook_duplicates(target_data, hooks_dir)
    hooks = target_data.setdefault("hooks", {})
    if not isinstance(hooks, dict):
        hooks = {}
        target_data["hooks"] = hooks
    for event_name, groups in package_data.get("hooks", {}).items():
        existing_groups = hooks.setdefault(event_name, [])
        if not isinstance(existing_groups, list):
            existing_groups = []
            hooks[event_name] = existing_groups
        for group in groups:
            existing_groups.append(group)
    recorder.write_text(target_hooks_path, json.dumps(target_data, indent=2, ensure_ascii=False) + "\n", reason="merge_hooks_json")
    return {"path": str(target_hooks_path), "removed_old_handlers": removed, "installed_events": sorted(package_data.get("hooks", {}).keys())}


def install_hook_scripts(archive_root: Path, hooks_dir: Path, recorder: ChangeRecorder) -> Dict[str, Any]:
    ensure_dir(hooks_dir, dry_run=recorder.dry_run)
    src_dir = archive_root / ".codex" / "hooks"
    copied: List[str] = []
    for name in HOOK_SCRIPT_FILES:
        recorder.copy_file(src_dir / name, hooks_dir / name)
        copied.append(str(hooks_dir / name))
    tests_src = src_dir / "tests"
    recorder.copy_tree(tests_src, hooks_dir / "tests")
    copied.append(str(hooks_dir / "tests"))
    archived: List[str] = []
    for name in LEGACY_HOOK_FILES:
        path = hooks_dir / name
        if path.exists():
            recorder.remove_path(path, reason="remove_legacy_hook")
            archived.append(str(path))
    return {"enabled": True, "hooks_dir": str(hooks_dir), "copied": copied, "removed_legacy": archived}


def detect_install(root: Path, *, global_mode: bool = False) -> Dict[str, Any]:
    detected: Dict[str, Any] = {
        "state": None,
        "skill_dirs": [],
        "hook_files": [],
        "custom_agents": [],
        "root_docs": [],
        "agents_blocks": False,
        "hooks_json_entries": False,
        "versions": [],
    }
    state_path = (root / ".codex-hybrid" / "bootstrap.state.json") if not global_mode else (root / "bootstrap.state.json")
    if state_path.exists():
        try:
            data = json.loads(state_path.read_text(encoding="utf-8"))
            detected["state"] = str(state_path)
            if isinstance(data, dict):
                detected["versions"].append({"package_name": data.get("package_name"), "package_version": data.get("package_version"), "path": str(state_path)})
        except Exception:
            detected["state"] = str(state_path)
    skills_root = (personal_skills_home() if global_mode else root / ".agents" / "skills")
    if skills_root.exists():
        for alias in LEGACY_ALIASES:
            p = skills_root / alias
            if p.exists():
                detected["skill_dirs"].append(str(p))
    hooks_dir = (root / "hooks") if global_mode else (root / ".codex" / "hooks")
    if hooks_dir.exists():
        for name in ALL_KNOWN_HOOK_NAMES:
            p = hooks_dir / name
            if p.exists():
                detected["hook_files"].append(str(p))
    agents_dir = (root / "agents") if global_mode else (root / ".codex" / "agents")
    if agents_dir.exists():
        for p in agents_dir.glob("*.toml"):
            if any(fnmatch.fnmatch(p.name, pat) for pat in LEGACY_AGENT_PATTERNS) and is_managed_file(p):
                detected["custom_agents"].append(str(p))
    if not global_mode:
        for name in LEGACY_ROOT_DOC_NAMES + ROOT_DOCS_TO_COPY:
            p = root / name
            if p.exists() and is_managed_file(p):
                detected["root_docs"].append(str(p))
        agents = root / "AGENTS.md"
        if agents.exists():
            text = read_text(agents)
            if any(alias in text for alias in LEGACY_ALIASES) or MANAGED_START in text:
                detected["agents_blocks"] = True
    else:
        override = root / "AGENTS.override.md"
        if override.exists():
            text = read_text(override)
            if any(alias in text for alias in LEGACY_ALIASES) or MANAGED_START in text:
                detected["agents_blocks"] = True
    hooks_json = (root / "hooks.json") if global_mode else (root / ".codex" / "hooks.json")
    if hooks_json.exists():
        try:
            data = json.loads(read_text(hooks_json))
            text = json.dumps(data, ensure_ascii=False)
        except Exception:
            text = read_text(hooks_json)
        detected["hooks_json_entries"] = any(alias in text for alias in LEGACY_ALIASES) or any(name in text for name in ALL_KNOWN_HOOK_NAMES)
    return detected


def remove_legacy_skill_dirs(skills_root: Path, recorder: ChangeRecorder) -> None:
    for alias in LEGACY_ALIASES:
        if alias == PACKAGE_NAME:
            continue
        p = skills_root / alias
        if p.exists():
            recorder.remove_path(p, reason="remove_legacy_skill_dir")


def remove_legacy_agents(agents_dir: Path, recorder: ChangeRecorder) -> None:
    if not agents_dir.exists():
        return
    for p in agents_dir.glob("*.toml"):
        if any(fnmatch.fnmatch(p.name, pat) for pat in LEGACY_AGENT_PATTERNS) and p.name not in CUSTOM_AGENTS and is_managed_file(p):
            recorder.remove_path(p, reason="remove_legacy_custom_agent")


def choose_root_doc_destination(repo_root: Path, doc_name: str) -> Path:
    # Keep archive root HOW_TO.md, but avoid clobbering user documents in target workspaces.
    if doc_name in ROOT_DOC_MANAGED_SUFFIXES:
        direct = repo_root / doc_name
        suffixed = repo_root / ROOT_DOC_MANAGED_SUFFIXES[doc_name]
        if not direct.exists() or is_managed_file(direct):
            return direct
        return suffixed
    return repo_root / doc_name


def run_profile_builder(archive_root: Path, workspace: Path, out_dir: Path, source_paths: List[Path], *, dry_run: bool) -> Dict[str, Any]:
    if dry_run:
        return {"dry_run": True, "would_write": [str(out_dir / "profile.md"), str(out_dir / "mapping.md"), str(out_dir / "inventory.json")]}
    builder = archive_root / ".agents" / "skills" / PACKAGE_NAME / "scripts" / "build_hybrid_profile.py"
    cmd = [sys.executable, str(builder), "--workspace", str(workspace), "--archive-root", str(archive_root), "--out", str(out_dir)]
    for source in source_paths:
        cmd.extend(["--source", str(source)])
    proc = subprocess.run(cmd, capture_output=True, text=True, check=True)
    try:
        return json.loads(proc.stdout)
    except Exception:
        return {"stdout": proc.stdout.strip(), "stderr": proc.stderr.strip()}


def discover_default_sources(target_root: Path, archive_root: Path, explicit: List[str]) -> List[Path]:
    if explicit:
        return [Path(p).expanduser().resolve() for p in explicit]
    sources = [target_root]
    if archive_root != target_root:
        sources.append(archive_root)
    return sources


def install_repo(archive_root: Path, repo_root: Path, source_paths: List[Path], enable_hooks: bool, args: argparse.Namespace) -> Dict[str, Any]:
    old = detect_install(repo_root)
    backup_parent = repo_root / ".codex-hybrid" / "backups"
    backup_root = make_backup_root(backup_parent, args.backup_dir, dry_run=args.dry_run) if args.replace_existing else None
    recorder = ChangeRecorder(dry_run=args.dry_run, replace_existing=args.replace_existing, backup_root=backup_root, base_root=repo_root)
    if old and any(v for v in old.values() if v):
        recorder.warnings.append("managed old/partial install detected; replacement is backup-first" if args.replace_existing else "managed old/partial install detected; pass --replace-existing to replace it")

    ensure_dir(repo_root / ".agents" / "skills", dry_run=args.dry_run)
    ensure_dir(repo_root / ".codex" / "agents", dry_run=args.dry_run)
    ensure_dir(repo_root / ".codex-hybrid", dry_run=args.dry_run)

    skills_root = repo_root / ".agents" / "skills"
    if args.replace_existing:
        remove_legacy_skill_dirs(skills_root, recorder)
    recorder.copy_tree(archive_root / ".agents" / "skills" / PACKAGE_NAME, skills_root / PACKAGE_NAME)

    agents_dir = repo_root / ".codex" / "agents"
    if args.replace_existing:
        remove_legacy_agents(agents_dir, recorder)
    for agent_name in CUSTOM_AGENTS:
        recorder.copy_file(archive_root / ".codex" / "agents" / agent_name, agents_dir / agent_name)

    doc_dests: Dict[str, str] = {}
    for doc_name in ROOT_DOCS_TO_COPY:
        dest = choose_root_doc_destination(repo_root, doc_name)
        recorder.copy_file(archive_root / doc_name, dest)
        doc_dests[doc_name] = str(dest)
    for rel_name in DOC_FILES_TO_COPY + TOOL_FILES_TO_COPY:
        recorder.copy_file(archive_root / rel_name, repo_root / rel_name)
    recorder.copy_file(archive_root / ".codex" / "config.toml.example", repo_root / ".codex" / "config.toml.example")
    for wrapper in INSTALL_WRAPPERS:
        dest = repo_root / wrapper
        if dest.exists() and not is_managed_file(dest):
            dest = repo_root / f"install.codex-claude-unison{Path(wrapper).suffix}"
        recorder.copy_file(archive_root / wrapper, dest)

    how_to_path = Path(doc_dests.get("HOW_TO.md", str(repo_root / "HOW_TO.md")))
    how_to_name = how_to_path.name if how_to_path.parent.resolve() == repo_root.resolve() else "HOW_TO.md"
    agents_merge = merge_agents_file(repo_root / "AGENTS.md", archive_root / "AGENTS.md", how_to_name, recorder)
    config_update = update_codex_config(repo_root / ".codex" / "config.toml", enable_hooks, recorder)

    hooks_path: Optional[Path] = None
    hook_install: Dict[str, Any] = {"enabled": False, "skipped": bool(not enable_hooks)}
    hooks_json_summary: Optional[Dict[str, Any]] = None
    if enable_hooks:
        hooks_dir = repo_root / ".codex" / "hooks"
        hook_install = install_hook_scripts(archive_root, hooks_dir, recorder)
        hooks_json_summary = merge_hooks_json(repo_root / ".codex" / "hooks.json", hooks_dir, recorder)
        hooks_path = repo_root / ".codex" / "hooks.json"
        hook_install["hooks_json"] = str(hooks_path)
    else:
        recorder.warnings.append("hooks skipped; verifier will use hookless fallback rules from bootstrap.state.json")

    profile_out = repo_root / ".codex-hybrid"
    builder_summary = run_profile_builder(archive_root, repo_root, profile_out, source_paths, dry_run=args.dry_run)

    state = {
        "package_name": PACKAGE_NAME,
        "package_version": PACKAGE_VERSION,
        "mode": "repo",
        "platform": sys.platform,
        "target_root": str(repo_root),
        "archive_root": str(archive_root),
        "hooks_enabled": enable_hooks,
        "hook_install": hook_install,
        "how_to": how_to_name,
        "source_paths": [str(p) for p in source_paths],
        "builder_summary": builder_summary,
        "backup_path": str(backup_root) if backup_root else None,
    }
    recorder.write_text(profile_out / "bootstrap.state.json", json.dumps(state, indent=2, ensure_ascii=False) + "\n", reason="write_bootstrap_state")
    backup_manifest_path = recorder.finalize_backup_manifest()

    return {
        "target_root": str(repo_root),
        "old_versions_detected": old,
        "backup_path": str(backup_root) if backup_root else None,
        "backup_manifest": backup_manifest_path,
        "config": config_update,
        "hooks": str(hooks_path) if hooks_path else None,
        "hooks_json": hooks_json_summary,
        "profile": str(profile_out / "profile.md"),
        "mapping": str(profile_out / "mapping.md"),
        "inventory": str(profile_out / "inventory.json"),
        "state": str(profile_out / "bootstrap.state.json"),
        "agents_merge": agents_merge,
        "hook_install": hook_install,
        "files_copied": recorder.files_copied,
        "files_replaced": recorder.files_replaced,
        "files_removed": recorder.files_removed,
        "files_skipped": recorder.files_skipped,
        "config_edits": recorder.config_edits,
        "warnings": recorder.warnings,
    }


def install_global(archive_root: Path, enable_hooks: bool, args: argparse.Namespace) -> Dict[str, Any]:
    codex_dir = codex_home()
    old = detect_install(codex_dir, global_mode=True)
    backup_parent = codex_dir / "backups"
    backup_root = make_backup_root(backup_parent, args.backup_dir, dry_run=args.dry_run) if args.replace_existing else None
    recorder = ChangeRecorder(dry_run=args.dry_run, replace_existing=args.replace_existing, backup_root=backup_root, base_root=codex_dir)

    skills_root = personal_skills_home()
    ensure_dir(skills_root, dry_run=args.dry_run)
    if args.replace_existing:
        remove_legacy_skill_dirs(skills_root, recorder)
    recorder.copy_tree(archive_root / ".agents" / "skills" / PACKAGE_NAME, skills_root / PACKAGE_NAME)

    ensure_dir(codex_dir, dry_run=args.dry_run)
    agents_dir = codex_dir / "agents"
    ensure_dir(agents_dir, dry_run=args.dry_run)
    if args.replace_existing:
        remove_legacy_agents(agents_dir, recorder)
    for agent_name in CUSTOM_AGENTS:
        recorder.copy_file(archive_root / ".codex" / "agents" / agent_name, agents_dir / agent_name)
    global_merge = merge_global_override(codex_dir / "AGENTS.override.md", recorder)
    config_update = update_codex_config(codex_dir / "config.toml", enable_hooks, recorder)

    hooks_path: Optional[Path] = None
    hook_install: Dict[str, Any] = {"enabled": False, "skipped": bool(not enable_hooks)}
    hooks_json_summary: Optional[Dict[str, Any]] = None
    if enable_hooks:
        hooks_dir = codex_dir / "hooks"
        hook_install = install_hook_scripts(archive_root, hooks_dir, recorder)
        hooks_json_summary = merge_hooks_json(codex_dir / "hooks.json", hooks_dir, recorder)
        hooks_path = codex_dir / "hooks.json"
        hook_install["hooks_json"] = str(hooks_path)
    backup_manifest_path = recorder.finalize_backup_manifest()
    return {
        "target_root": str(codex_dir),
        "old_versions_detected": old,
        "backup_path": str(backup_root) if backup_root else None,
        "backup_manifest": backup_manifest_path,
        "config": config_update,
        "agents_dir": str(agents_dir),
        "skill_dir": str(skills_root / PACKAGE_NAME),
        "global_override": global_merge,
        "hooks": str(hooks_path) if hooks_path else None,
        "hooks_json": hooks_json_summary,
        "hook_install": hook_install,
        "files_copied": recorder.files_copied,
        "files_replaced": recorder.files_replaced,
        "files_removed": recorder.files_removed,
        "files_skipped": recorder.files_skipped,
        "config_edits": recorder.config_edits,
        "warnings": recorder.warnings,
    }


def resolve_mode(requested: str, target: Path) -> str:
    if requested != "auto":
        return requested
    # Auto is intentionally workspace-first. A git repo gets a repo-root install;
    # a non-git workspace still gets a local repo-style install rather than a
    # surprising global install.
    return "repo"


def main(argv: Sequence[str]) -> int:
    args = parse_args(argv)
    target = Path(args.target).expanduser().resolve()
    archive_root = find_archive_root(Path(__file__).resolve())
    resolved_repo = workspace_root(target)
    mode = resolve_mode(args.mode, target)
    enable_hooks = not args.skip_hooks
    source_paths = discover_default_sources(resolved_repo, archive_root, args.source)

    summary: Dict[str, Any] = {
        "package_name": PACKAGE_NAME,
        "package_version": PACKAGE_VERSION,
        "archive_root": str(archive_root),
        "requested_mode": args.mode,
        "resolved_mode": mode,
        "target_root": str(resolved_repo),
        "platform": sys.platform,
        "python": str(Path(sys.executable).resolve()),
        "dry_run": bool(args.dry_run),
        "replace_existing": bool(args.replace_existing),
        "hooks_enabled": enable_hooks if mode in {"repo", "both", "global"} else False,
        "repo": None,
        "global": None,
        "verification_hints": [],
        "warnings": [],
    }
    if args.skip_hooks:
        summary["warnings"].append("Hooks were skipped by request; AGENTS/profile remain the hookless fallback.")

    if mode in {"repo", "both"}:
        summary["repo"] = install_repo(archive_root, resolved_repo, source_paths, enable_hooks, args)
        summary["verification_hints"].append(f"{sys.executable} {resolved_repo / 'tools' / 'verify_bundle.py'} --json")
    if mode in {"global", "both"}:
        summary["global"] = install_global(archive_root, enable_hooks, args)
        summary["verification_hints"].append("Global installs are verified indirectly by repo sessions; inspect ~/.codex/hooks.json and ~/.agents/skills/codex-claude-unison if needed.")

    for section in ("repo", "global"):
        value = summary.get(section)
        if isinstance(value, dict):
            summary["warnings"].extend(value.get("warnings", []))

    if args.json:
        print(json.dumps(summary, indent=2, ensure_ascii=False))
    else:
        print(f"[{PACKAGE_NAME}] version={PACKAGE_VERSION} mode={mode} platform={sys.platform}{' dry-run' if args.dry_run else ''}")
        if summary["repo"]:
            repo_summary = summary["repo"]
            print(f"  repo/workspace root: {repo_summary['target_root']}")
            print(f"  profile:             {repo_summary['profile']}")
            print(f"  mapping:             {repo_summary['mapping']}")
            print(f"  inventory:           {repo_summary['inventory']}")
            print(f"  state:               {repo_summary['state']}")
            if repo_summary.get("backup_path"):
                print(f"  backup:              {repo_summary['backup_path']}")
            if repo_summary.get("hooks"):
                print(f"  hooks:               {repo_summary['hooks']}")
        if summary["global"]:
            global_summary = summary["global"]
            print(f"  codex home:          {global_summary['target_root']}")
            print(f"  skill dir:           {global_summary['skill_dir']}")
            print(f"  agents dir:          {global_summary['agents_dir']}")
            if global_summary.get("backup_path"):
                print(f"  global backup:       {global_summary['backup_path']}")
            if global_summary.get("hooks"):
                print(f"  global hooks:        {global_summary['hooks']}")
        for warning in summary["warnings"]:
            print(f"  warning: {warning}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
