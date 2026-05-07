#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import re
import shlex
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

PACKAGE_VERSION = "2026-04-28-v2.3"
MAX_COMMAND_LOG = 32
MAX_SUMMARY_CHARS = 2000
MAX_TRANSCRIPT_READ_BYTES = 2_000_000
MAX_STDIN_EVENT_BYTES = 10_000_000

FAILURE_MESSAGE = "A command in this turn failed. Do not claim success; either fix it or report the failure faithfully."

SUCCESS_PATTERN = re.compile(
    r"(?:\b(done|complete(?:d)?|finished|fixed|all tests? pass(?:ed)?|tests? pass(?:ed)?|verified|working|successful(?:ly)?)\b|готово|исправлен[оы]?|выполнен[оы]?|тесты? пройден[ыо]|проверен[оы]?|работает)",
    re.IGNORECASE,
)

HONEST_FAILURE_PATTERN = re.compile(
    r"(?:\b(fail(?:ed|ure)?|error|errors|could not verify|couldn't verify|unable to verify|did not pass|still failing|not verified|unverified|blocked|could not complete|couldn't complete|tests? failed|build failed|lint failed|type ?check failed)\b|ошибк|не удалось|не смог|не смогл|не проверен|не удалось проверить|не прошло|не пройден|падает|упал|сбой|заблокирован)",
    re.IGNORECASE,
)

EXIT_CODE_KEYS = (
    "exit_code",
    "exitCode",
    "returncode",
    "return_code",
    "returnCode",
    "status",
    "statusCode",
    "code",
)

TOOL_ID_KEYS = (
    "tool_use_id",
    "toolUseId",
    "tool_call_id",
    "toolCallId",
    "call_id",
    "callId",
    "id",
)

EVENT_TYPE_KEYS = ("type", "event", "event_type", "eventType", "kind", "name")

PROVIDER_ERROR_PATTERN = re.compile(
    r"(?:provider[_ -]?error|api[_ -]?error|rate[_ -]?limit|context[_ -]?overflow|max[_ -]?tokens|overloaded|gateway|network[_ -]?error|timeout|authentication|credential)",
    re.IGNORECASE,
)


def event_indicates_provider_issue(event: Dict[str, Any]) -> bool:
    """Return True for runtime/provider failures where a stop hook should not create a retry loop."""
    try:
        compact = json.dumps(event, ensure_ascii=False)[:4000]
    except Exception:
        compact = str(event)[:4000]
    return bool(PROVIDER_ERROR_PATTERN.search(compact))


@dataclass(frozen=True)
class ExitCodeEvidence:
    exit_code: Optional[int]
    source: str


def _read_stdin_limited() -> Tuple[str, bool]:
    stdin_buffer = getattr(sys.stdin, "buffer", None)
    if stdin_buffer is not None:
        raw_bytes = stdin_buffer.read(MAX_STDIN_EVENT_BYTES + 1)
        if len(raw_bytes) > MAX_STDIN_EVENT_BYTES:
            return "", True
        return raw_bytes.decode("utf-8", errors="replace"), False
    raw = sys.stdin.read(MAX_STDIN_EVENT_BYTES + 1)
    if len(raw.encode("utf-8", errors="ignore")) > MAX_STDIN_EVENT_BYTES:
        return "", True
    return raw, False


def read_event() -> Dict[str, Any]:
    raw, too_large = _read_stdin_limited()
    if too_large:
        return {
            "_unison_error": "stdin_too_large",
            "_unison_max_stdin_event_bytes": MAX_STDIN_EVENT_BYTES,
        }
    if not raw.strip():
        return {}
    try:
        parsed = json.loads(raw)
        return parsed if isinstance(parsed, dict) else {}
    except Exception:
        return {}


def find_repo_root(start: Path) -> Path:
    try:
        start = start.resolve()
    except Exception:
        start = Path.cwd()
    if start.is_file():
        start = start.parent
    for candidate in [start, *start.parents]:
        if (candidate / ".git").exists():
            return candidate
    return start


def repo_from_event(event: Dict[str, Any]) -> Path:
    cwd = event.get("cwd")
    if not isinstance(cwd, str) or not cwd:
        cwd = os.getcwd()
    return find_repo_root(Path(cwd))


def hybrid_dir(repo_root: Path) -> Path:
    return repo_root / ".codex-hybrid"


def ensure_guard_dir(repo_root: Path) -> Path:
    path = hybrid_dir(repo_root) / "guard"
    path.mkdir(parents=True, exist_ok=True)
    return path


def load_json(path: Path, default: Any) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default


def dump_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def bootstrap_state(repo_root: Path) -> Dict[str, Any]:
    value = load_json(hybrid_dir(repo_root) / "bootstrap.state.json", {})
    return value if isinstance(value, dict) else {}


def bootstrap_missing_or_stale(repo_root: Path) -> bool:
    state = bootstrap_state(repo_root)
    return state.get("package_version") != PACKAGE_VERSION


def managed_profile_exists(repo_root: Path) -> bool:
    return (hybrid_dir(repo_root) / "profile.md").exists()


def _parse_json_string_maybe(value: Any) -> Any:
    if not isinstance(value, str):
        return value
    stripped = value.strip()
    if not stripped or stripped[0] not in "[{":
        return value
    try:
        return json.loads(stripped)
    except Exception:
        return value


def tool_response_payload(tool_response: Any) -> Any:
    return _parse_json_string_maybe(tool_response)


def _walk_values(value: Any) -> Iterable[Any]:
    yield value
    if isinstance(value, dict):
        for child in value.values():
            yield from _walk_values(child)
    elif isinstance(value, list):
        for child in value:
            yield from _walk_values(child)


def tool_response_text(tool_response: Any) -> str:
    """Return text only for summaries. Never use this as shell failure evidence."""
    value = tool_response_payload(tool_response)
    if isinstance(value, str):
        return value
    if isinstance(value, dict):
        parts: List[str] = []
        for key in ("stdout", "stderr", "output", "text", "message", "content"):
            child = value.get(key)
            if isinstance(child, str) and child:
                parts.append(child)
        if parts:
            return "\n".join(parts)
        try:
            return json.dumps(value, ensure_ascii=False)
        except Exception:
            return ""
    try:
        return json.dumps(value, ensure_ascii=False)
    except Exception:
        return str(value)


def _coerce_int(value: Any) -> Optional[int]:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, float) and value.is_integer():
        return int(value)
    if isinstance(value, str) and re.fullmatch(r"-?\d+", value.strip()):
        try:
            return int(value.strip())
        except Exception:
            return None
    return None


def _extract_exit_code_from_obj(value: Any) -> Optional[int]:
    if isinstance(value, dict):
        for key in EXIT_CODE_KEYS:
            if key in value:
                coerced = _coerce_int(value.get(key))
                if coerced is not None:
                    return coerced
    for child in _walk_values(value):
        if isinstance(child, dict):
            for key in EXIT_CODE_KEYS:
                if key in child:
                    coerced = _coerce_int(child.get(key))
                    if coerced is not None:
                        return coerced
    return None


def extract_exit_code(tool_response: Any) -> Optional[int]:
    return _extract_exit_code_from_obj(tool_response_payload(tool_response))


def _contains_tool_use_id(value: Any, tool_use_id: str) -> bool:
    if not tool_use_id:
        return False
    if isinstance(value, dict):
        for key, child in value.items():
            if key in TOOL_ID_KEYS and child == tool_use_id:
                return True
            if _contains_tool_use_id(child, tool_use_id):
                return True
    elif isinstance(value, list):
        return any(_contains_tool_use_id(child, tool_use_id) for child in value)
    elif isinstance(value, str):
        return value == tool_use_id
    return False


def _contains_event_type(value: Any, expected: str) -> bool:
    expected_norm = expected.lower()
    if isinstance(value, dict):
        for key, child in value.items():
            if key in EVENT_TYPE_KEYS and isinstance(child, str):
                norm = child.lower().replace("-", "_").replace(".", "_")
                if expected_norm in norm:
                    return True
            if _contains_event_type(child, expected):
                return True
    elif isinstance(value, list):
        return any(_contains_event_type(child, expected) for child in value)
    return False


def _read_transcript_tail(path: Path) -> List[str]:
    try:
        size = path.stat().st_size
        with path.open("rb") as fh:
            if size > MAX_TRANSCRIPT_READ_BYTES:
                fh.seek(max(0, size - MAX_TRANSCRIPT_READ_BYTES))
                data = fh.read()
                first_nl = data.find(b"\n")
                if first_nl >= 0:
                    data = data[first_nl + 1 :]
            else:
                data = fh.read()
        return data.decode("utf-8", errors="replace").splitlines()
    except Exception:
        return []


def extract_exit_code_from_transcript(transcript_path: Any, tool_use_id: Any) -> Optional[int]:
    if not isinstance(transcript_path, str) or not transcript_path:
        return None
    if not isinstance(tool_use_id, str) or not tool_use_id:
        return None
    path = Path(transcript_path).expanduser()
    if not path.exists() or not path.is_file():
        return None

    for line in reversed(_read_transcript_tail(path)):
        # Fast guard: avoid parsing unrelated transcript lines.
        if tool_use_id not in line:
            continue
        if "exec_command_end" not in line and "exit_code" not in line and "exitCode" not in line:
            continue
        try:
            event = json.loads(line)
        except Exception:
            continue
        if not _contains_tool_use_id(event, tool_use_id):
            continue
        if not _contains_event_type(event, "exec_command_end"):
            continue
        exit_code = _extract_exit_code_from_obj(event)
        if exit_code is not None:
            return exit_code
    return None


def resolve_exit_code(event: Dict[str, Any], tool_response: Any) -> ExitCodeEvidence:
    structured = extract_exit_code(tool_response)
    if structured is not None:
        return ExitCodeEvidence(structured, "tool_response")
    transcript = extract_exit_code_from_transcript(event.get("transcript_path"), event.get("tool_use_id"))
    if transcript is not None:
        return ExitCodeEvidence(transcript, "transcript")
    return ExitCodeEvidence(None, "unavailable")


def summarize_text(text: str, limit: int = MAX_SUMMARY_CHARS) -> str:
    cleaned = text.strip()
    if len(cleaned) <= limit:
        return cleaned
    return cleaned[: limit - 1] + "…"


def _split_command_segments(command: str) -> List[str]:
    # This is intentionally shallow. It is a classifier, not a shell parser.
    raw_segments = re.split(r"\s*(?:&&|\|\||;|\|)\s*", command.strip())
    return [segment for segment in raw_segments if segment.strip()]


def _tokenize(segment: str) -> List[str]:
    try:
        return shlex.split(segment, posix=(os.name != "nt"))
    except Exception:
        return segment.strip().split()


def _command_basename(token: str) -> str:
    token = token.strip().strip('"\'')
    # Make Windows paths work even when this code runs on POSIX, and vice versa.
    token = re.split(r"[/\\]+", token)[-1]
    lower = token.lower()
    for suffix in (".exe", ".cmd", ".bat", ".ps1"):
        if lower.endswith(suffix):
            lower = lower[: -len(suffix)]
            break
    return lower


def _strip_env_assignments(tokens: Sequence[str]) -> List[str]:
    out = list(tokens)
    while out and re.match(r"^[A-Za-z_][A-Za-z0-9_]*=", out[0]):
        out.pop(0)
    if out and _command_basename(out[0]) == "env":
        out.pop(0)
        while out and (out[0].startswith("-") or re.match(r"^[A-Za-z_][A-Za-z0-9_]*=", out[0])):
            out.pop(0)
    if out and _command_basename(out[0]) in {"sudo", "doas"}:
        out.pop(0)
    return out


def _segments_tokens(command: str) -> Iterable[List[str]]:
    for segment in _split_command_segments(command):
        tokens = _strip_env_assignments(_tokenize(segment))
        if tokens:
            yield tokens


def command_expected_nonzero(command: str, exit_code: Optional[int] = None) -> bool:
    if exit_code != 1:
        return False
    for tokens in _segments_tokens(command):
        cmd = _command_basename(tokens[0])
        args = [t.lower() for t in tokens[1:]]
        if cmd in {"grep", "rg", "ripgrep", "findstr"}:
            return True
        if cmd == "which":
            return True
        if cmd == "command" and args[:1] == ["-v"]:
            return True
        if cmd in {"test", "["}:
            return True
        if cmd == "cmp":
            return True
        if cmd == "git" and args[:1] == ["diff"] and any(a in {"--quiet", "-q"} for a in args):
            return True
        if cmd == "diff" and any(a in {"--quiet", "-q"} for a in args):
            return True
    return False


def _has_script_name(args: Sequence[str], names: Iterable[str]) -> bool:
    wanted = {name.lower() for name in names}
    for arg in args:
        normalized = arg.lower().replace("_", "-")
        if normalized in wanted:
            return True
    return False


def command_is_verification(command: str) -> bool:
    """Conservative verification detector. Avoid broad words like any 'build' substring."""
    for tokens in _segments_tokens(command):
        cmd = _command_basename(tokens[0])
        args = [a.lower() for a in tokens[1:]]

        if cmd in {"pytest", "py.test", "jest", "vitest", "rspec", "phpunit", "eslint", "stylelint", "shellcheck", "flake8", "mypy", "pyright", "ruff"}:
            return True
        if cmd == "tsc":
            return True
        if cmd in {"npm", "pnpm", "yarn"}:
            if args[:1] == ["test"]:
                return True
            if args[:1] == ["build"]:
                return True
            if args[:1] == ["lint"]:
                return True
            if args[:1] == ["run"] and len(args) >= 2 and args[1] in {"test", "tests", "lint", "typecheck", "type-check", "check", "build", "verify"}:
                return True
        if cmd == "bun":
            if args[:1] in (["test"], ["build"]):
                return True
            if args[:1] == ["run"] and len(args) >= 2 and args[1] in {"test", "tests", "lint", "typecheck", "type-check", "check", "build", "verify"}:
                return True
        if cmd == "cargo" and args[:1] and args[0] in {"test", "check", "build", "clippy"}:
            return True
        if cmd == "go" and args[:1] and args[0] in {"test", "vet", "build"}:
            return True
        if cmd == "dotnet" and args[:1] and args[0] in {"test", "build"}:
            return True
        if cmd in {"mvn", "mvnw"} and any(a in {"test", "verify", "package"} for a in args):
            return True
        if cmd in {"gradle", "gradlew"} and any(a in {"test", "check", "build"} for a in args):
            return True
        if cmd in {"make", "gmake", "ninja"} and _has_script_name(args, {"test", "check", "lint", "typecheck", "type-check", "build", "verify"}):
            return True
        if cmd in {"python", "python3", "py"}:
            if "-m" in args:
                idx = args.index("-m")
                module = args[idx + 1] if idx + 1 < len(args) else ""
                if module in {"pytest", "unittest", "mypy", "py_compile", "compileall", "ruff", "flake8"}:
                    return True
    return False


def classify_command(event: Dict[str, Any], command: str, tool_response: Any) -> Tuple[bool, ExitCodeEvidence, bool]:
    evidence = resolve_exit_code(event, tool_response)
    expected = command_expected_nonzero(command, evidence.exit_code)
    if evidence.exit_code is None:
        return False, evidence, expected
    if evidence.exit_code == 0:
        return False, evidence, expected
    if expected:
        return False, evidence, expected
    return True, evidence, expected


def assistant_claims_success(message: str) -> bool:
    return bool(SUCCESS_PATTERN.search(message or ""))


def assistant_reports_failure(message: str) -> bool:
    return bool(HONEST_FAILURE_PATTERN.search(message or ""))


def turn_state_path(repo_root: Path) -> Path:
    return ensure_guard_dir(repo_root) / "unison_turn_state.v2.json"


def seed_turn_state(turn_id: str) -> Dict[str, Any]:
    return {
        "schema": "codex-claude-unison.turn-state.v2",
        "package_version": PACKAGE_VERSION,
        "turn_id": turn_id,
        "commands": [],
        "failure_count": 0,
        "last_failure_index": None,
        "last_successful_verification_index": None,
        "stop_block_count": 0,
    }


def load_turn_state(repo_root: Path, turn_id: str) -> Dict[str, Any]:
    state = load_json(turn_state_path(repo_root), {})
    if not isinstance(state, dict) or state.get("turn_id") != turn_id:
        return seed_turn_state(turn_id)
    state.setdefault("schema", "codex-claude-unison.turn-state.v2")
    state.setdefault("package_version", PACKAGE_VERSION)
    state.setdefault("commands", [])
    state.setdefault("failure_count", 0)
    state.setdefault("last_failure_index", None)
    state.setdefault("last_successful_verification_index", None)
    state.setdefault("stop_block_count", 0)
    return state


def write_turn_state(repo_root: Path, state: Dict[str, Any]) -> None:
    dump_json(turn_state_path(repo_root), state)


def reset_turn_state(repo_root: Path, turn_id: str) -> None:
    write_turn_state(repo_root, seed_turn_state(turn_id))


def record_command_result(
    repo_root: Path,
    turn_id: str,
    command: str,
    event: Dict[str, Any],
    tool_response: Any,
    *,
    is_verification: bool,
) -> Dict[str, Any]:
    state = load_turn_state(repo_root, turn_id)
    text = tool_response_text(tool_response)
    failed, evidence, expected_nonzero = classify_command(event, command, tool_response)
    record = {
        "command": command,
        "is_verification": is_verification,
        "failed": failed,
        "exit_code": evidence.exit_code,
        "exit_code_source": evidence.source,
        "expected_nonzero": expected_nonzero,
        "summary": summarize_text(text),
    }
    state["commands"] = (state.get("commands") or [])[-(MAX_COMMAND_LOG - 1) :] + [record]
    index = len(state["commands"]) - 1
    if failed:
        state["failure_count"] = int(state.get("failure_count") or 0) + 1
        state["last_failure_index"] = index
    elif is_verification and evidence.exit_code == 0:
        state["last_successful_verification_index"] = index
    write_turn_state(repo_root, state)
    return state


def unresolved_turn_failure(state: Dict[str, Any]) -> bool:
    last_failure_index = state.get("last_failure_index")
    if last_failure_index is None:
        return False
    last_success_index = state.get("last_successful_verification_index")
    return last_success_index is None or int(last_success_index) < int(last_failure_index)


def latest_failure(state: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    commands = state.get("commands") or []
    last_failure_index = state.get("last_failure_index")
    if last_failure_index is None:
        return None
    try:
        idx = int(last_failure_index)
    except Exception:
        return None
    if 0 <= idx < len(commands):
        value = commands[idx]
        if isinstance(value, dict):
            return value
    return None


def increment_stop_block_count(repo_root: Path, state: Dict[str, Any]) -> Dict[str, Any]:
    state["stop_block_count"] = int(state.get("stop_block_count") or 0) + 1
    write_turn_state(repo_root, state)
    return state


def json_print(data: Dict[str, Any]) -> None:
    print(json.dumps(data, ensure_ascii=False))


def safe_run(fn) -> int:
    try:
        return int(fn() or 0)
    except Exception:
        # Hooks are guardrails, not a reason to break the entire Codex turn.
        return 0
