#!/usr/bin/env python3
from __future__ import annotations

import argparse
import ast
import json
import os
import subprocess
import tempfile
import sys
from pathlib import Path
from typing import Any, Dict, List

ROOT = Path(__file__).resolve().parents[1]
STATE = ROOT / ".codex-hybrid" / "bootstrap.state.json"

BASE_REQUIRED_FILES = [
    "AGENTS.md",
    "HOW_TO.md",
    "README.md",
    "HYBRID_MODEL_INSTRUCTIONS.md",
    "ONE_ARCHIVE_MANIFEST.json",
    "MIGRATION_NOTES.md",
    "install.sh",
    "install.ps1",
    "install.cmd",
    ".agents/skills/codex-claude-unison/SKILL.md",
    ".agents/skills/codex-claude-unison/scripts/bootstrap_portable.py",
    ".agents/skills/codex-claude-unison/scripts/build_hybrid_profile.py",
    ".agents/skills/codex-claude-unison/scripts/bootstrap.sh",
    ".agents/skills/codex-claude-unison/scripts/bootstrap.ps1",
    ".agents/skills/codex-claude-unison/scripts/bootstrap.cmd",
    ".codex/agents/unison-mapper.toml",
    ".codex/agents/unison-reviewer.toml",
    ".codex/agents/unison-implementer.toml",
    ".codex/agents/unison-verifier.toml",
    "tools/persist_tool_result.py",
    "tools/context_doctor.py",
    "tools/tests/run_tool_fixtures.py",
    "tools/tests/run_installer_fixtures.py",
    "docs/context-hygiene.md",
    "docs/retry-policy.md",
    "docs/plan-handoff-template.md",
]

HOOK_REQUIRED_FILES = [
    ".codex/hooks/common.py",
    ".codex/hooks/context_hook.py",
    ".codex/hooks/pre_tool_use_guard.py",
    ".codex/hooks/post_tool_use_guard.py",
    ".codex/hooks/stop_turn_guard.py",
    ".codex/hooks/tests/run_fixtures.py",
]

BASE_PY_COMPILE_FILES = [
    ".agents/skills/codex-claude-unison/scripts/bootstrap_portable.py",
    ".agents/skills/codex-claude-unison/scripts/build_hybrid_profile.py",
    "tools/persist_tool_result.py",
    "tools/context_doctor.py",
    "tools/tests/run_tool_fixtures.py",
    "tools/tests/run_installer_fixtures.py",
]

HOOK_PY_COMPILE_FILES = [
    ".codex/hooks/common.py",
    ".codex/hooks/context_hook.py",
    ".codex/hooks/pre_tool_use_guard.py",
    ".codex/hooks/post_tool_use_guard.py",
    ".codex/hooks/stop_turn_guard.py",
    ".codex/hooks/tests/run_fixtures.py",
]


def load_state() -> Dict[str, Any]:
    try:
        data = json.loads(STATE.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def hooks_expected() -> bool:
    state = load_state()
    if state and state.get("hooks_enabled") is False:
        return False
    return True


def run(cmd: List[str], *, env: Dict[str, str] | None = None, timeout: int = 120) -> Dict[str, Any]:
    merged_env = os.environ.copy()
    if env:
        merged_env.update(env)
    # Use temporary files instead of PIPEs. Some hook fixtures spawn nested
    # subprocesses; file-backed capture avoids rare pipe EOF hangs while keeping
    # deterministic stdout/stderr in the JSON report.
    with tempfile.NamedTemporaryFile("w+b", delete=False) as out_fh, tempfile.NamedTemporaryFile("w+b", delete=False) as err_fh:
        out_path = Path(out_fh.name)
        err_path = Path(err_fh.name)
        try:
            proc = subprocess.run(cmd, cwd=ROOT, stdout=out_fh, stderr=err_fh, timeout=timeout, env=merged_env)
        finally:
            out_fh.flush()
            err_fh.flush()
    try:
        stdout = out_path.read_text(encoding="utf-8", errors="replace")
        stderr = err_path.read_text(encoding="utf-8", errors="replace")
    finally:
        try:
            out_path.unlink()
        except Exception:
            pass
        try:
            err_path.unlink()
        except Exception:
            pass
    return {
        "cmd": cmd,
        "returncode": proc.returncode,
        "stdout": stdout,
        "stderr": stderr,
        "ok": proc.returncode == 0,
    }


def check_required() -> Dict[str, Any]:
    required = list(BASE_REQUIRED_FILES)
    skipped: List[str] = []
    if hooks_expected():
        required.extend(HOOK_REQUIRED_FILES)
    else:
        skipped.extend(HOOK_REQUIRED_FILES)
    missing = [rel for rel in required if not (ROOT / rel).exists()]
    return {"ok": not missing, "missing": missing, "skipped_hook_files": skipped, "hooks_expected": hooks_expected()}


def check_py_compile() -> Dict[str, Any]:
    files = list(BASE_PY_COMPILE_FILES)
    skipped: List[str] = []
    if hooks_expected():
        files.extend(HOOK_PY_COMPILE_FILES)
    else:
        skipped.extend(HOOK_PY_COMPILE_FILES)
    missing = [rel for rel in files if not (ROOT / rel).exists()]
    if missing:
        return {
            "cmd": [sys.executable, "-m", "py_compile", *files],
            "returncode": 1,
            "stdout": "",
            "stderr": "missing files: " + ", ".join(missing),
            "ok": False,
            "missing": missing,
            "skipped_hook_compile": skipped,
        }
    result = run([sys.executable, "-m", "py_compile", *files], timeout=180)
    result["missing"] = []
    result["skipped_hook_compile"] = skipped
    return result


def check_no_legacy_agent_defaults() -> Dict[str, Any]:
    offenders: List[str] = []
    for rel in [".codex/config.toml.example", ".agents/skills/codex-claude-unison/scripts/bootstrap_portable.py"]:
        path = ROOT / rel
        if not path.exists():
            continue
        text = path.read_text(encoding="utf-8")
        if "max_threads = 6" in text or "max_depth = 1" in text:
            offenders.append(rel)
    return {"ok": not offenders, "offenders": offenders}


def check_manifest() -> Dict[str, Any]:
    path = ROOT / "ONE_ARCHIVE_MANIFEST.json"
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        return {"ok": False, "error": str(exc)}
    expected = [
        "docs/context-hygiene.md",
        "tools/persist_tool_result.py",
        "tools/context_doctor.py",
        "tools/tests/run_tool_fixtures.py",
        "tools/tests/run_installer_fixtures.py",
        "install.sh",
        "install.ps1",
        "install.cmd",
    ]
    serialized = json.dumps(data, ensure_ascii=False)
    missing = [item for item in expected if item not in serialized]
    return {"ok": not missing and data.get("name") == "codex-claude-unison", "missing": missing, "version": data.get("version")}


GENERATED_REFERENCE_PREFIXES = (
    ".codex-hybrid/profile.md",
    ".codex-hybrid/mapping.md",
    ".codex-hybrid/inventory.json",
    ".codex-hybrid/plans/",
    ".codex-hybrid/tool-results/",
)


def check_referenced_files_exist() -> Dict[str, Any]:
    texts = []
    for rel in ["README.md", "HOW_TO.md", "ONE_ARCHIVE_MANIFEST.json", "MIGRATION_NOTES.md"]:
        path = ROOT / rel
        if path.exists():
            texts.append(path.read_text(encoding="utf-8", errors="ignore"))
    joined = "\n".join(texts)
    referenced = sorted(set(part.strip("`'\" ,)") for part in joined.split() if "/" in part and (part.endswith(".py") or part.endswith(".md") or part.endswith(".sh") or part.endswith(".ps1") or part.endswith(".cmd"))))
    missing = []
    ignored_generated = []
    for rel in referenced:
        if rel.startswith("/") or rel.startswith("~"):
            continue
        if rel.startswith(GENERATED_REFERENCE_PREFIXES):
            ignored_generated.append(rel)
            continue
        if not (ROOT / rel).exists():
            missing.append(rel)
    return {"ok": not missing, "missing": missing[:50], "referenced_count": len(referenced), "ignored_generated": ignored_generated}


def test_commands(include_installer_tests: bool) -> List[List[str]]:
    commands: List[List[str]] = []
    # Run tool tests before hook tests. Some Python runtimes can leave subprocess
    # pipe state awkward after the hook fixture suite because that suite itself
    # spawns hooks repeatedly; this order is deterministic and avoids a false
    # verifier hang while preserving all checks.
    commands.append([sys.executable, "tools/tests/run_tool_fixtures.py", "-v"])
    if hooks_expected():
        commands.append([sys.executable, ".codex/hooks/tests/run_fixtures.py", "-v"])
    # Installer fixtures require a full source payload, including hook source files.
    # A hookless installed tree is valid and intentionally lacks .codex/hooks, so
    # it verifies its installed invariants and tool helpers but skips migration
    # fixture recursion. The source archive still runs the installer suite.
    if include_installer_tests and hooks_expected():
        commands.append([sys.executable, "tools/tests/run_installer_fixtures.py", "-v"])
    return commands


def verify(include_installer_tests: bool) -> Dict[str, Any]:
    required = check_required()
    tests = [run(cmd, env={"UNISON_VERIFY_NO_INSTALLER": "1"} if "run_installer_fixtures.py" not in cmd[-2:] else None, timeout=180) for cmd in test_commands(include_installer_tests)] if required.get("ok") else []
    compile_result = check_py_compile() if required["ok"] else {"ok": False, "skipped": "missing required files"}
    no_legacy = check_no_legacy_agent_defaults()
    manifest = check_manifest()
    refs = check_referenced_files_exist()
    checks = {
        "required_files": required,
        "py_compile": compile_result,
        "tests": tests,
        "multi_agent_v2_legacy_defaults": no_legacy,
        "manifest": manifest,
        "referenced_files_exist": refs,
    }
    ok = required["ok"] and compile_result.get("ok") and all(t["ok"] for t in tests) and no_legacy["ok"] and manifest["ok"] and refs["ok"]
    return {"ok": bool(ok), "root": str(ROOT), "hooks_expected": hooks_expected(), "checks": checks}


def main(argv: List[str]) -> int:
    parser = argparse.ArgumentParser(description="Verify the Codex-Claude Unison portable bundle.")
    parser.add_argument("--json", action="store_true", help="Print JSON report.")
    parser.add_argument("--skip-installer-tests", action="store_true", help="Skip installer smoke/migration tests.")
    args = parser.parse_args(argv)
    include_installer = not args.skip_installer_tests and os.environ.get("UNISON_VERIFY_NO_INSTALLER") != "1"
    report = verify(include_installer)
    if args.json:
        print(json.dumps(report, indent=2, ensure_ascii=False))
    else:
        print(f"Bundle verification: {'OK' if report['ok'] else 'FAILED'}")
        for name, value in report["checks"].items():
            if name == "tests":
                print(f"- {name}: {'OK' if all(t['ok'] for t in value) else 'FAILED'}")
            else:
                print(f"- {name}: {'OK' if value.get('ok') else 'FAILED'}")
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
