#!/usr/bin/env python3
from __future__ import annotations

import importlib.util
import contextlib
import io
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from typing import Any, Dict, List

ROOT = Path(__file__).resolve().parents[2]
BOOTSTRAP = ROOT / ".agents" / "skills" / "codex-claude-unison" / "scripts" / "bootstrap_portable.py"
VERIFY_ENV = {**os.environ, "UNISON_VERIFY_NO_INSTALLER": "1"}


def load_bootstrap() -> Any:
    spec = importlib.util.spec_from_file_location("bootstrap_portable_v23", BOOTSTRAP)
    if spec is None or spec.loader is None:
        raise AssertionError(f"Could not load {BOOTSTRAP}")
    module = importlib.util.module_from_spec(spec)
    sys.modules["bootstrap_portable_v23"] = module
    spec.loader.exec_module(module)
    return module



def run(cmd: List[str], cwd: Path | None = None, env: Dict[str, str] | None = None) -> subprocess.CompletedProcess[str]:
    merged = os.environ.copy()
    if env:
        merged.update(env)
    with tempfile.NamedTemporaryFile("w+b", delete=False) as out_fh, tempfile.NamedTemporaryFile("w+b", delete=False) as err_fh:
        out_path = Path(out_fh.name)
        err_path = Path(err_fh.name)
        proc = subprocess.run(cmd, cwd=str(cwd or ROOT), stdout=out_fh, stderr=err_fh, timeout=180, env=merged)
    try:
        stdout = out_path.read_text(encoding="utf-8", errors="replace")
        stderr = err_path.read_text(encoding="utf-8", errors="replace")
    finally:
        for path in (out_path, err_path):
            try:
                path.unlink()
            except Exception:
                pass
    return subprocess.CompletedProcess(cmd, proc.returncode, stdout, stderr)


def make_repo() -> tempfile.TemporaryDirectory[str]:
    td = tempfile.TemporaryDirectory()
    root = Path(td.name)
    (root / ".git").mkdir()
    return td


def run_bootstrap(target: Path, *extra: str) -> Dict[str, Any]:
    """Run bootstrap through its real CLI parser without spawning a nested Python process.

    The source verifier still exercises this file as an executable. The fixture uses
    in-process execution to stay deterministic on CI/sandbox systems where nested
    Python subprocess capture can hang.
    """
    bootstrap = load_bootstrap()
    argv = ["--mode", "repo", "--target", str(target), "--replace-existing", "--yes", "--json", *extra]
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        rc = bootstrap.main(argv)
    if rc != 0:
        raise AssertionError(f"bootstrap failed\nargv={argv}\nstdout={buf.getvalue()}")
    return json.loads(buf.getvalue())


def run_installed_verify(repo: Path) -> Dict[str, Any]:
    """Check installed package invariants without recursively running nested fixtures.

    Full hook/tool/installer fixture execution happens once from the source verifier.
    Smoke installs use this lightweight verifier to avoid recursive test loops while
    still proving that the installed tree is complete and self-consistent.
    """
    verify = repo / "tools" / "verify_bundle.py"
    spec = importlib.util.spec_from_file_location("installed_verify_bundle", verify)
    if spec is None or spec.loader is None:
        raise AssertionError(f"Could not load installed verifier at {verify}")
    module = importlib.util.module_from_spec(spec)
    sys.modules["installed_verify_bundle"] = module
    spec.loader.exec_module(module)
    required = module.check_required()
    no_legacy = module.check_no_legacy_agent_defaults()
    manifest = module.check_manifest()
    refs = module.check_referenced_files_exist()
    hooks_expected = module.hooks_expected()
    report = {
        "ok": bool(required.get("ok") and no_legacy.get("ok") and manifest.get("ok") and refs.get("ok")),
        "checks": {
            "required_files": required,
            "py_compile": "covered by source verifier",
            "tests": "covered by source verifier",
            "multi_agent_v2_legacy_defaults": no_legacy,
            "manifest": manifest,
            "referenced_files_exist": refs,
        },
        "hooks_expected": hooks_expected,
    }
    if not report.get("ok"):
        raise AssertionError(f"installed verify failed: {json.dumps(report, ensure_ascii=False)[:2000]}")
    return report


def count_managed_blocks(text: str) -> int:
    return text.count("<!-- codex-claude-unison:start -->")


class InstallerFixtureTests(unittest.TestCase):
    def test_hook_enabled_repo_install_smoke(self) -> None:
        with make_repo() as td:
            repo = Path(td)
            summary = run_bootstrap(repo)
            self.assertTrue((repo / ".codex" / "hooks.json").exists())
            self.assertTrue(summary["repo"]["hook_install"]["enabled"])
            report = run_installed_verify(repo)
            self.assertTrue(report["ok"], report)

    def test_hookless_repo_install_smoke(self) -> None:
        with make_repo() as td:
            repo = Path(td)
            summary = run_bootstrap(repo, "--skip-hooks")
            self.assertFalse(summary["repo"]["hook_install"].get("enabled", False))
            state = json.loads((repo / ".codex-hybrid" / "bootstrap.state.json").read_text(encoding="utf-8"))
            self.assertFalse(state["hooks_enabled"])
            report = run_installed_verify(repo)
            self.assertTrue(report["ok"], report)
            self.assertFalse(report["hooks_expected"])

    def test_replacement_from_old_partial_install_backup_prune_and_verify(self) -> None:
        with make_repo() as td:
            repo = Path(td)
            # Existing user content must survive.
            (repo / "AGENTS.md").write_text(
                "# User rules\nKeep this line.\n\n"
                "<!-- codex-claude-hybrid:start -->\nold managed block\n<!-- codex-claude-hybrid:end -->\n",
                encoding="utf-8",
            )
            old_skill = repo / ".agents" / "skills" / "codex-claude-hybrid"
            old_skill.mkdir(parents=True)
            (old_skill / "SKILL.md").write_text("old codex-claude-hybrid skill", encoding="utf-8")
            old_hooks = repo / ".codex" / "hooks"
            old_hooks.mkdir(parents=True)
            (old_hooks / "post_tool_use_review.py").write_text("# codex-claude-unison old hook\n", encoding="utf-8")
            (old_hooks / "stop_enforcer.py").write_text("# codex-claude-unison old hook\n", encoding="utf-8")
            old_agents = repo / ".codex" / "agents"
            old_agents.mkdir(parents=True)
            (old_agents / "hybrid-reviewer.toml").write_text('name="hybrid_reviewer"\ndescription="codex-claude-unison old"\n', encoding="utf-8")
            hooks_json = repo / ".codex" / "hooks.json"
            hooks_json.write_text(json.dumps({"hooks": {"PostToolUse": [{"hooks": [{"type": "command", "command": "python .codex/hooks/post_tool_use_review.py"}]}], "Stop": [{"hooks": [{"type": "command", "command": "python .codex/hooks/stop_enforcer.py"}]}]}}), encoding="utf-8")
            config = repo / ".codex" / "config.toml"
            config.write_text("[features]\nmulti_agent_v2 = true\n\n[agents]\nmax_threads = 6\nmax_depth = 1\n", encoding="utf-8")
            state_dir = repo / ".codex-hybrid"
            state_dir.mkdir(parents=True)
            (state_dir / "bootstrap.state.json").write_text(json.dumps({"package_name": "codex-claude-hybrid", "package_version": "old"}), encoding="utf-8")
            (state_dir / "profile.md").write_text("old profile", encoding="utf-8")
            (state_dir / "mapping.md").write_text("old mapping", encoding="utf-8")
            (state_dir / "inventory.json").write_text("{}", encoding="utf-8")

            summary = run_bootstrap(repo)
            repo_summary = summary["repo"]
            backup = Path(repo_summary["backup_path"])
            self.assertTrue(backup.exists(), repo_summary)
            self.assertTrue((backup / "backup_manifest.json").exists())
            self.assertFalse(old_skill.exists())
            self.assertFalse((old_hooks / "post_tool_use_review.py").exists())
            self.assertTrue((repo / ".agents" / "skills" / "codex-claude-unison" / "SKILL.md").exists())
            self.assertTrue((repo / ".codex" / "agents" / "unison-reviewer.toml").exists())
            self.assertFalse((repo / ".codex" / "agents" / "hybrid-reviewer.toml").exists())
            agents_text = (repo / "AGENTS.md").read_text(encoding="utf-8")
            self.assertIn("Keep this line.", agents_text)
            self.assertEqual(count_managed_blocks(agents_text), 1)
            hooks_text = hooks_json.read_text(encoding="utf-8")
            self.assertNotIn("post_tool_use_review.py", hooks_text)
            self.assertNotIn("stop_enforcer.py", hooks_text)
            config_text = config.read_text(encoding="utf-8")
            self.assertIn("multi_agent_v2 = true", config_text)
            self.assertIn("codex_hooks = true", config_text)
            self.assertNotIn("max_threads", config_text)
            self.assertNotIn("max_depth", config_text)
            report = run_installed_verify(repo)
            self.assertTrue(report["ok"], report)

    def test_merge_agents_file_preserves_user_content_and_replaces_managed_blocks(self) -> None:
        bootstrap = load_bootstrap()
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            target = root / "AGENTS.md"
            target.write_text(
                "# User rules\n"
                "Keep this line.\n\n"
                "<!-- codex-claude-hybrid:start -->\n"
                "old managed block\n"
                "<!-- codex-claude-hybrid:end -->\n\n"
                "Middle user note.\n\n"
                "<!-- codex-claude-unison-portable-full: begin -->\n"
                "older managed block\n"
                "<!-- codex-claude-unison-portable-full: end -->\n"
                "Tail user note.\n",
                encoding="utf-8",
            )
            backup = root / "backup"
            recorder = bootstrap.ChangeRecorder(
                dry_run=False,
                replace_existing=True,
                backup_root=backup,
                base_root=root,
            )
            summary = bootstrap.merge_agents_file(target, ROOT / "AGENTS.md", "HOW_TO.md", recorder)

            text = target.read_text(encoding="utf-8")
            self.assertEqual(summary["managed_blocks_removed"], 2)
            self.assertIn("Keep this line.", text)
            self.assertIn("Middle user note.", text)
            self.assertIn("Tail user note.", text)
            self.assertNotIn("old managed block", text)
            self.assertNotIn("older managed block", text)
            self.assertEqual(count_managed_blocks(text), 1)
            self.assertTrue((backup / "AGENTS.md").exists())

    def test_idempotence_no_duplicate_hooks_or_agents_blocks(self) -> None:
        with make_repo() as td:
            repo = Path(td)
            run_bootstrap(repo)
            first_hooks = json.loads((repo / ".codex" / "hooks.json").read_text(encoding="utf-8"))
            first_agents = (repo / "AGENTS.md").read_text(encoding="utf-8")
            run_bootstrap(repo)
            second_hooks = json.loads((repo / ".codex" / "hooks.json").read_text(encoding="utf-8"))
            second_agents = (repo / "AGENTS.md").read_text(encoding="utf-8")
            self.assertEqual(count_managed_blocks(second_agents), 1)
            self.assertEqual(count_managed_blocks(first_agents), 1)
            self.assertEqual(len(json.dumps(first_hooks)), len(json.dumps(second_hooks)))
            for event, groups in second_hooks.get("hooks", {}).items():
                commands = []
                for group in groups:
                    for handler in group.get("hooks", []):
                        command = handler.get("command")
                        if command and "codex-claude-unison" in command:
                            commands.append(command)
                self.assertEqual(len(commands), len(set(commands)), event)

    def test_hooks_json_prune_preserves_unrelated_same_filename_hooks(self) -> None:
        bootstrap = load_bootstrap()
        with make_repo() as td:
            repo = Path(td)
            hooks_dir = repo / ".codex" / "hooks"
            hooks_dir.mkdir(parents=True)
            hooks_json = repo / ".codex" / "hooks.json"
            unrelated_command = "python /opt/company/hooks/context_hook.py"
            old_managed_command = f"python {hooks_dir / 'post_tool_use_guard.py'}"
            hooks_json.write_text(
                json.dumps(
                    {
                        "hooks": {
                            "UserPromptSubmit": [{"hooks": [{"type": "command", "command": unrelated_command}]}],
                            "PostToolUse": [{"hooks": [{"type": "command", "command": old_managed_command}]}],
                        }
                    }
                ),
                encoding="utf-8",
            )
            recorder = bootstrap.ChangeRecorder(dry_run=False, replace_existing=True, backup_root=repo / "backup", base_root=repo)
            summary = bootstrap.merge_hooks_json(hooks_json, hooks_dir, recorder)
            text = hooks_json.read_text(encoding="utf-8")
            self.assertEqual(summary["removed_old_handlers"], 1)
            self.assertIn(unrelated_command, text)
            self.assertNotIn(old_managed_command, text)

    def test_config_regression_preserves_unrelated_config(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            config = Path(td) / "config.toml"
            config.write_text("[features]\nmulti_agent_v2 = true\nother = false\n\n[agents]\nmax_threads = 6\nmax_depth = 1\n\n[profiles.main]\nmodel = \"x\"\n", encoding="utf-8")
            load_bootstrap().ensure_codex_config(config, enable_hooks=True)
            text = config.read_text(encoding="utf-8")
            self.assertIn("multi_agent_v2 = true", text)
            self.assertIn("other = false", text)
            self.assertIn("codex_hooks = true", text)
            self.assertIn("[profiles.main]", text)
            self.assertNotIn("max_threads", text)
            self.assertNotIn("max_depth", text)

    def test_dry_run_reports_without_modifying(self) -> None:
        with make_repo() as td:
            repo = Path(td)
            (repo / "AGENTS.md").write_text("# User content\n", encoding="utf-8")
            before = {p.relative_to(repo).as_posix(): p.read_bytes() for p in repo.rglob("*") if p.is_file()}
            bootstrap = load_bootstrap()
            buf = io.StringIO()
            with contextlib.redirect_stdout(buf):
                rc = bootstrap.main(["--mode", "repo", "--target", str(repo), "--replace-existing", "--dry-run", "--json"])
            self.assertEqual(rc, 0, buf.getvalue())
            summary = json.loads(buf.getvalue())
            self.assertTrue(summary["dry_run"])
            after = {p.relative_to(repo).as_posix(): p.read_bytes() for p in repo.rglob("*") if p.is_file()}
            self.assertEqual(before, after)

    def test_windows_path_logic_is_not_bash_dependent_and_quotes_spaces(self) -> None:
        command = load_bootstrap().script_command(Path("C:/Users/Name With Spaces/.codex/hooks/post_tool_use_guard.py"))
        self.assertNotIn("bash", command.lower())
        self.assertNotIn("/bin/sh", command.lower())
        self.assertIn("post_tool_use_guard.py", command)
        self.assertTrue('"' in command or "Name With Spaces" in command)


if __name__ == "__main__":
    unittest.main(verbosity=2)
