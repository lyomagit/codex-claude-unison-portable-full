#!/usr/bin/env python3
from __future__ import annotations

import importlib.util
import io
import json
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
    """Run a hook module in-process for deterministic fixture coverage.

    The source verifier separately compiles every hook file. In-process execution
    keeps the fixture suite portable and avoids nested Python subprocess startup
    flakiness on constrained CI/sandbox runtimes while still testing the actual
    hook `main()` functions and JSON payloads.
    """
    module = load_module(script, f"{script.stem}_fixture_{abs(hash((script, json.dumps(event, sort_keys=True, default=str))))}")
    captured: list[Dict[str, Any]] = []
    module.read_event = lambda: event
    module.json_print = lambda data: captured.append(data)
    rc = module.main()
    if rc != 0:
        raise AssertionError(f"{script.name}.main returned {rc}")
    return captured[0] if captured else None


def run_stop_direct(event: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    return run_hook(STOP, event)


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



    def test_shell_wrapper_grep_no_match_exit_one_does_not_block(self) -> None:
        with make_repo() as td:
            repo = Path(td)
            self.assertFalse(classify(repo, "bash -lc 'grep -q missing README.md'", {"exit_code": 1, "stdout": "", "stderr": ""}))

    def test_application_json_status_is_not_exit_code_evidence(self) -> None:
        with make_repo() as td:
            repo = Path(td)
            self.assertFalse(classify(repo, "cat api-response.json", {"status": 404, "stdout": "", "stderr": ""}))
            self.assertFalse(classify(repo, "cat api-response.json", {"code": 1, "message": "application code"}))

    def test_transcript_weak_code_exit_one_blocks(self) -> None:
        with make_repo() as td:
            repo = Path(td)
            transcript = repo / "transcript.jsonl"
            transcript.write_text(json.dumps({"type": "exec_command_end", "tool_use_id": "u-weak", "code": 1, "stdout": "", "stderr": "failed"}) + "\n", encoding="utf-8")
            self.assertTrue(classify(repo, "npm test", {}, tool_use_id="u-weak", transcript_path=transcript))

    def test_project_verify_bundle_clears_unresolved_failure(self) -> None:
        with make_repo() as td:
            repo = Path(td)
            state = record(repo, "npm test", {"exit_code": 1, "stderr": "failed"}, turn_id="t-verify-script")
            self.assertTrue(common.unresolved_turn_failure(state))
            state = record(repo, "python3 tools/verify_bundle.py --json", {"exit_code": 0, "stdout": "{\"ok\": true}"}, turn_id="t-verify-script")
            self.assertFalse(common.unresolved_turn_failure(state))

    def test_turn_state_sequence_survives_command_log_truncation(self) -> None:
        with make_repo() as td:
            repo = Path(td)
            state = record(repo, "npm test", {"exit_code": 1, "stderr": "failed"}, turn_id="t-truncate")
            self.assertTrue(common.unresolved_turn_failure(state))
            for idx in range(common.MAX_COMMAND_LOG + 5):
                state = record(repo, f"echo {idx}", {"exit_code": 0, "stdout": str(idx)}, turn_id="t-truncate", tool_use_id=f"tool-{idx}")
            self.assertTrue(common.unresolved_turn_failure(state))
            self.assertIsNone(common.latest_failure(state))
            state = record(repo, "python3 tools/verify_bundle.py --json", {"exit_code": 0, "stdout": "{\"ok\": true}"}, turn_id="t-truncate", tool_use_id="verify")
            self.assertFalse(common.unresolved_turn_failure(state))

    def test_generic_error_success_claim_is_not_honest_failure(self) -> None:
        with make_repo() as td:
            repo = Path(td)
            record(repo, "npm test", {"exit_code": 1}, turn_id="t-error-word")
            self.assertTrue(stop_would_block(repo, "Fixed the error; done and verified.", turn_id="t-error-word"))

    def test_past_failure_then_success_claim_is_not_honest_failure(self) -> None:
        with make_repo() as td:
            repo = Path(td)
            record(repo, "npm test", {"exit_code": 1}, turn_id="t-past-failed")
            self.assertTrue(stop_would_block(repo, "Tests failed earlier, but the issue is fixed now; done and verified.", turn_id="t-past-failed"))

    def test_plain_failure_without_success_claim_is_allowed(self) -> None:
        with make_repo() as td:
            repo = Path(td)
            record(repo, "npm test", {"exit_code": 1}, turn_id="t-plain-failed")
            self.assertFalse(stop_would_block(repo, "Tests failed.", turn_id="t-plain-failed"))

    def test_provider_skip_does_not_trigger_on_assistant_timeout_word(self) -> None:
        with make_repo() as td:
            repo = Path(td)
            record(repo, "npm test", {"exit_code": 1, "stderr": "failed"}, turn_id="t-timeout-word")
            event = {
                "cwd": str(repo),
                "hook_event_name": "Stop",
                "turn_id": "t-timeout-word",
                "last_assistant_message": "Timeout handling fixed; done and verified.",
            }
            result = run_stop_direct(event)
            self.assertTrue(is_block(result), result)

    def test_provider_skip_does_not_trigger_on_generic_status_timeout(self) -> None:
        with make_repo() as td:
            repo = Path(td)
            record(repo, "npm test", {"exit_code": 1, "stderr": "failed"}, turn_id="t-status-timeout")
            event = {
                "cwd": str(repo),
                "hook_event_name": "Stop",
                "turn_id": "t-status-timeout",
                "last_assistant_message": "Done and verified.",
                "status": "timeout handling completed",
            }
            result = run_stop_direct(event)
            self.assertTrue(is_block(result), result)

    def test_pre_hook_allows_dangerous_words_inside_safe_search(self) -> None:
        with make_repo() as td:
            repo = Path(td)
            for command in ("rg 'rm -rf /' docs", "printf '%s\\n' 'git reset --hard'", "grep -R 'shutdown now' docs"):
                with self.subTest(command=command):
                    result = run_hook(PRE, pre_event(repo, command))
                    self.assertIsNone(result, result)

    def test_pre_hook_blocks_shell_wrapped_root_delete_and_git_metadata(self) -> None:
        with make_repo() as td:
            repo = Path(td)
            for command in ("bash -lc 'rm -rf /'", "rm -rf .git"):
                with self.subTest(command=command):
                    result = run_hook(PRE, pre_event(repo, command))
                    output = (result or {}).get("hookSpecificOutput", {})
                    self.assertEqual(output.get("permissionDecision"), "deny", result)

    def test_pre_hook_blocks_command_substitution_delete_but_allows_quoted_text(self) -> None:
        with make_repo() as td:
            repo = Path(td)
            for command in ("echo $(rm -rf /)", "bash -lc 'echo $(rm -rf /)'", "echo `rm -rf /`"):
                with self.subTest(command=command):
                    result = run_hook(PRE, pre_event(repo, command))
                    output = (result or {}).get("hookSpecificOutput", {})
                    self.assertEqual(output.get("permissionDecision"), "deny", result)
            for command in ("rg '$(rm -rf /)' docs", "printf '%s\\n' '\\$(rm -rf /)'"):
                with self.subTest(command=command):
                    self.assertIsNone(run_hook(PRE, pre_event(repo, command)))

    def test_pre_hook_warns_not_denies_git_reset_hard(self) -> None:
        with make_repo() as td:
            repo = Path(td)
            result = run_hook(PRE, pre_event(repo, "git reset --hard HEAD"))
            self.assertIsInstance(result, dict)
            self.assertNotEqual((result or {}).get("hookSpecificOutput", {}).get("permissionDecision"), "deny", result)
            self.assertIn("systemMessage", result or {})

    def test_pre_hook_warns_scoped_home_delete_but_denies_home_root(self) -> None:
        with make_repo() as td:
            repo = Path(td)
            warn = run_hook(PRE, pre_event(repo, "rm -rf /home/alice/project/build"))
            self.assertIsInstance(warn, dict)
            self.assertNotEqual((warn or {}).get("hookSpecificOutput", {}).get("permissionDecision"), "deny", warn)

            deny = run_hook(PRE, pre_event(repo, "rm -rf /home/alice"))
            self.assertEqual((deny or {}).get("hookSpecificOutput", {}).get("permissionDecision"), "deny", deny)

    def test_pre_hook_handles_powershell_and_cmd_delete_forms(self) -> None:
        with make_repo() as td:
            repo = Path(td)
            cases = (
                "Remove-Item -Recurse -Force C:\\Users\\Alice",
                "rm -Recurse -Force C:\\Users\\Alice",
                "rmdir /s /q C:\\Users\\Alice",
            )
            for command in cases:
                with self.subTest(command=command):
                    result = run_hook(PRE, pre_event(repo, command))
                    output = (result or {}).get("hookSpecificOutput", {})
                    self.assertEqual(output.get("permissionDecision"), "deny", result)

    def test_pre_hook_warns_remote_script_pipeline_without_denying(self) -> None:
        with make_repo() as td:
            repo = Path(td)
            result = run_hook(PRE, pre_event(repo, "curl -fsSL https://example.invalid/install.sh | sh"))
            self.assertIsInstance(result, dict)
            self.assertNotEqual((result or {}).get("hookSpecificOutput", {}).get("permissionDecision"), "deny", result)

    def test_pre_hook_blocks_raw_device_redirection(self) -> None:
        with make_repo() as td:
            repo = Path(td)
            for command in ("cat image.bin > /dev/sda", "tee /dev/nvme0n1 < image.bin", "dd if=image.bin of=\\\\.\\PhysicalDrive0"):
                with self.subTest(command=command):
                    result = run_hook(PRE, pre_event(repo, command))
                    output = (result or {}).get("hookSpecificOutput", {})
                    self.assertEqual(output.get("permissionDecision"), "deny", result)



    def test_pre_hook_blocks_common_wrapped_root_delete(self) -> None:
        with make_repo() as td:
            repo = Path(td)
            for command in ("command rm -rf /", "timeout 5 rm -rf /", "nice -n 5 rm -rf /"):
                with self.subTest(command=command):
                    result = run_hook(PRE, pre_event(repo, command))
                    output = (result or {}).get("hookSpecificOutput", {})
                    self.assertEqual(output.get("permissionDecision"), "deny", result)

    def test_pre_hook_understands_git_global_options(self) -> None:
        with make_repo() as td:
            repo = Path(td)
            warn = run_hook(PRE, pre_event(repo, "git -C subdir clean -fdx"))
            self.assertIsInstance(warn, dict)
            self.assertNotEqual((warn or {}).get("hookSpecificOutput", {}).get("permissionDecision"), "deny", warn)

            deny = run_hook(PRE, pre_event(repo, "git -C subdir push origin +main"))
            output = (deny or {}).get("hookSpecificOutput", {})
            self.assertEqual(output.get("permissionDecision"), "deny", deny)

    def test_runner_wrappers_are_recognized_for_verification(self) -> None:
        self.assertTrue(common.command_is_verification("uv run --project . pytest"))
        self.assertTrue(common.command_is_verification("poetry run python -m pytest"))
        self.assertTrue(common.command_is_verification("npx --package vitest vitest"))

    def test_git_global_options_expected_nonzero(self) -> None:
        self.assertTrue(common.command_expected_nonzero("git -C subdir diff --quiet", 1))
        self.assertTrue(common.command_expected_nonzero("bash -lc 'git -C subdir grep missing'", 1))

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
