#!/usr/bin/env python3
from __future__ import annotations

import importlib.util
import io
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from typing import Any, Dict, Optional

HOOKS_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(HOOKS_DIR))

import common  # noqa: E402

POST = HOOKS_DIR / "post_tool_use_guard.py"
PRE = HOOKS_DIR / "pre_tool_use_guard.py"
STOP = HOOKS_DIR / "stop_turn_guard.py"
BOOTSTRAP = HOOKS_DIR.parents[1] / ".agents" / "skills" / "codex-claude-unison" / "scripts" / "bootstrap_portable.py"


def load_module(path: Path, name: str) -> Any:
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise AssertionError(f"Could not load {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def load_bootstrap_module() -> Any:
    return load_module(BOOTSTRAP, "bootstrap_portable")


def make_repo() -> tempfile.TemporaryDirectory[str]:
    td = tempfile.TemporaryDirectory()
    root = Path(td.name)
    (root / ".git").mkdir()
    return td


def post_event(repo: Path, command: str, response: Any, *, turn_id: str = "turn", tool_use_id: str = "tool", transcript_path: Optional[Path] = None) -> Dict[str, Any]:
    event: Dict[str, Any] = {
        "cwd": str(repo),
        "hook_event_name": "PostToolUse",
        "turn_id": turn_id,
        "tool_name": "Bash",
        "tool_use_id": tool_use_id,
        "tool_input": {"command": command},
        "tool_response": response,
    }
    if transcript_path is not None:
        event["transcript_path"] = str(transcript_path)
    return event


def pre_event(repo: Path, command: str) -> Dict[str, Any]:
    return {
        "cwd": str(repo),
        "hook_event_name": "PreToolUse",
        "tool_name": "Bash",
        "tool_input": {"command": command},
    }


def classify(repo: Path, command: str, response: Any, **kwargs: Any) -> bool:
    event = post_event(repo, command, response, **kwargs)
    failed, _, _ = common.classify_command(event, command, response)
    return failed


def record(repo: Path, command: str, response: Any, *, turn_id: str = "turn", tool_use_id: str = "tool", transcript_path: Optional[Path] = None) -> Dict[str, Any]:
    event = post_event(repo, command, response, turn_id=turn_id, tool_use_id=tool_use_id, transcript_path=transcript_path)
    return common.record_command_result(
        repo,
        turn_id,
        command,
        event,
        response,
        is_verification=common.command_is_verification(command),
    )


def stop_would_block(repo: Path, message: str, *, turn_id: str = "turn") -> bool:
    state = common.load_turn_state(repo, turn_id)
    if not common.unresolved_turn_failure(state):
        return False
    if common.assistant_reports_failure(message):
        return False
    return common.assistant_claims_success(message)


def run_hook(script: Path, event: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    payload = json.dumps(event, ensure_ascii=False)
    with tempfile.NamedTemporaryFile("w+", encoding="utf-8", delete=False) as in_fh, \
         tempfile.NamedTemporaryFile("w+b", delete=False) as out_fh, \
         tempfile.NamedTemporaryFile("w+b", delete=False) as err_fh:
        in_fh.write(payload)
        in_fh.flush()
        in_path = Path(in_fh.name)
        out_path = Path(out_fh.name)
        err_path = Path(err_fh.name)
        with in_path.open("r", encoding="utf-8") as stdin_fh:
            proc = subprocess.run(
                [sys.executable, str(script)],
                stdin=stdin_fh,
                stdout=out_fh,
                stderr=err_fh,
                timeout=10,
                cwd=str(event.get("cwd") or HOOKS_DIR),
            )
    try:
        stdout = out_path.read_text(encoding="utf-8", errors="replace")
        stderr = err_path.read_text(encoding="utf-8", errors="replace")
    finally:
        for path in (in_path, out_path, err_path):
            try:
                path.unlink()
            except Exception:
                pass
    if proc.returncode != 0:
        raise AssertionError(f"{script.name} exited {proc.returncode}\nstdout={stdout}\nstderr={stderr}")
    out = stdout.strip()
    return json.loads(out) if out else None



def run_stop_direct(event: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    module = load_module(STOP, "stop_turn_guard_fixture")
    captured: list[Dict[str, Any]] = []
    module.read_event = lambda: event
    module.json_print = lambda data: captured.append(data)
    rc = module.main()
    if rc != 0:
        raise AssertionError(f"stop_turn_guard.main returned {rc}")
    return captured[0] if captured else None


def is_block(result: Optional[Dict[str, Any]]) -> bool:
    return isinstance(result, dict) and result.get("decision") == "block"


class HookFixtureTests(unittest.TestCase):
    def test_read_event_rejects_oversized_stdin(self) -> None:
        original_stdin = sys.stdin
        try:
            sys.stdin = io.StringIO("x" * 10_000_001)
            event = common.read_event()
        finally:
            sys.stdin = original_stdin
        self.assertEqual(event.get("_unison_error"), "stdin_too_large")

    def test_exit_zero_with_request_failed_stdout_does_not_block(self) -> None:
        with make_repo() as td:
            repo = Path(td)
            self.assertFalse(classify(repo, "awk 'NR<=82{print}' file.md", {"exit_code": 0, "stdout": "Request failed is just text"}))

    def test_exit_zero_with_traceback_stdout_does_not_block(self) -> None:
        with make_repo() as td:
            repo = Path(td)
            self.assertFalse(classify(repo, "cat notes.txt", {"exit_code": 0, "stdout": "Traceback appears in docs"}))

    def test_exit_one_empty_stdout_blocks(self) -> None:
        with make_repo() as td:
            repo = Path(td)
            self.assertTrue(classify(repo, "npm test", {"exit_code": 1, "stdout": "", "stderr": ""}))

    def test_empty_tool_response_transcript_exit_one_blocks(self) -> None:
        with make_repo() as td:
            repo = Path(td)
            transcript = repo / "transcript.jsonl"
            transcript.write_text(json.dumps({"type": "exec_command_end", "tool_use_id": "u1", "exit_code": 1}) + "\n", encoding="utf-8")
            self.assertTrue(classify(repo, "npm test", {}, tool_use_id="u1", transcript_path=transcript))

    def test_empty_tool_response_transcript_exit_zero_scary_stdout_no_block(self) -> None:
        with make_repo() as td:
            repo = Path(td)
            transcript = repo / "transcript.jsonl"
            transcript.write_text(json.dumps({"type": "exec_command_end", "tool_use_id": "u2", "exit_code": 0, "stdout": "Request failed\nTraceback"}) + "\n", encoding="utf-8")
            self.assertFalse(classify(repo, "strings codex | grep Request", {}, tool_use_id="u2", transcript_path=transcript))

    def test_grep_no_match_exit_one_does_not_block(self) -> None:
        with make_repo() as td:
            repo = Path(td)
            self.assertFalse(classify(repo, "grep -q missing README.md", {"exit_code": 1, "stdout": "", "stderr": ""}))

    def test_real_lint_failure_nonzero_blocks(self) -> None:
        with make_repo() as td:
            repo = Path(td)
            self.assertTrue(classify(repo, "npm run lint", {"exit_code": 2, "stdout": "", "stderr": "lint failed"}))

    def test_successful_verification_clears_unresolved_failure(self) -> None:
        with make_repo() as td:
            repo = Path(td)
            state = record(repo, "npm test", {"exit_code": 1, "stderr": "failed"}, turn_id="t-clear", tool_use_id="a")
            self.assertTrue(common.unresolved_turn_failure(state))
            state = record(repo, "pytest", {"exit_code": 0, "stdout": "passed"}, turn_id="t-clear", tool_use_id="b")
            self.assertFalse(common.unresolved_turn_failure(state))

    def test_honest_failure_report_allowed_by_stop(self) -> None:
        with make_repo() as td:
            repo = Path(td)
            record(repo, "npm test", {"exit_code": 1}, turn_id="t-honest")
            self.assertFalse(stop_would_block(repo, "Tests failed; I could not verify the fix yet.", turn_id="t-honest"))

    def test_false_success_claim_after_unresolved_failure_is_blocked(self) -> None:
        with make_repo() as td:
            repo = Path(td)
            record(repo, "npm test", {"exit_code": 1}, turn_id="t-false")
            self.assertTrue(stop_would_block(repo, "Fixed, done, and verified.", turn_id="t-false"))


    def test_multi_agent_v2_config_conflict_is_removed_by_installer(self) -> None:
        bootstrap = load_bootstrap_module()
        with tempfile.TemporaryDirectory() as td:
            config = Path(td) / "config.toml"
            config.write_text(
                "[features]\n"
                "multi_agent_v2 = true\n"
                "\n"
                "[agents]\n"
                "max_threads = 6\n"
                "max_depth = 1\n",
                encoding="utf-8",
            )
            bootstrap.ensure_codex_config(config, enable_hooks=True)
            text = config.read_text(encoding="utf-8")
            self.assertIn("multi_agent_v2 = true", text)
            self.assertIn("codex_hooks = true", text)
            self.assertNotIn("max_threads", text)
            self.assertNotIn("max_depth", text)
            self.assertNotIn("[agents]", text)

    def test_post_hook_smoke_scary_stdout_no_block(self) -> None:
        with make_repo() as td:
            repo = Path(td)
            result = run_hook(POST, post_event(repo, "awk 'NR<=82{print}' file.md", {"exit_code": 0, "stdout": "Request failed"}, turn_id="smoke1"))
            self.assertIsNone(result)

    def test_post_hook_smoke_real_nonzero_blocks(self) -> None:
        with make_repo() as td:
            repo = Path(td)
            result = run_hook(POST, post_event(repo, "npm test", {"exit_code": 1, "stderr": "failed"}, turn_id="smoke2"))
            self.assertTrue(is_block(result), result)

    def test_pre_hook_blocks_absolute_recursive_rm_variants(self) -> None:
        with make_repo() as td:
            repo = Path(td)
            for command in ("rm -rf /*", "rm -rf /home", "rm -rf --no-preserve-root /"):
                with self.subTest(command=command):
                    result = run_hook(PRE, pre_event(repo, command))
                    output = (result or {}).get("hookSpecificOutput", {})
                    self.assertEqual(output.get("permissionDecision"), "deny", result)


    def test_stop_hook_blocks_once_then_allows_to_avoid_death_spiral(self) -> None:
        with make_repo() as td:
            repo = Path(td)
            record(repo, "npm test", {"exit_code": 1, "stderr": "failed"}, turn_id="t-loop")
            event = {
                "cwd": str(repo),
                "hook_event_name": "Stop",
                "turn_id": "t-loop",
                "last_assistant_message": "Done and verified.",
            }
            first = run_stop_direct(event)
            self.assertTrue(is_block(first), first)
            second = run_stop_direct(event)
            self.assertFalse(is_block(second), second)

    def test_stop_hook_skips_provider_error_context(self) -> None:
        with make_repo() as td:
            repo = Path(td)
            record(repo, "npm test", {"exit_code": 1, "stderr": "failed"}, turn_id="t-provider")
            event = {
                "cwd": str(repo),
                "hook_event_name": "Stop",
                "turn_id": "t-provider",
                "last_assistant_message": "Done and verified.",
                "error": "provider_error: rate_limit timeout",
            }
            result = run_stop_direct(event)
            self.assertFalse(is_block(result), result)


if __name__ == "__main__":
    unittest.main(verbosity=2)
