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

PACKAGE_VERSION = "2026-05-17-v3.1.1"
TURN_STATE_SCHEMA = "codex-claude-unison.turn-state.v3"
MAX_COMMAND_LOG = 32
MAX_SUMMARY_CHARS = 2000
MAX_TRANSCRIPT_READ_BYTES = 2_000_000
MAX_STDIN_EVENT_BYTES = 10_000_000

FAILURE_MESSAGE = "A command in this turn failed. Do not claim success; either fix it or report the failure faithfully."

SUCCESS_PATTERN = re.compile(
    r"(?:\b(done|all set|complete(?:d)?|finished|fixed|all tests? pass(?:ed)?|tests? pass(?:ed)?|verified|working|successful(?:ly)?)\b|готово|сделан[оы]?|исправлен[оы]?|выполнен[оы]?|тесты? пройден[ыо]|проверен[оы]?|работает|успешн[оы]?)",
    re.IGNORECASE,
)

HONEST_FAILURE_PATTERN = re.compile(
    r"(?:"
    r"\b(could not verify|couldn't verify|unable to verify|did not pass|still failing|not verified|unverified|could not complete|couldn't complete)\b"
    r"|\b(?:tests?|build|lint|type ?check)\b.{0,80}\b(?:did not pass|still failing|not fixed|not resolved|unresolved)\b"
    r"|\b(?:failed|failure)\b.{0,80}\b(?:remain|remaining|still|unresolved|not fixed|not resolved|persist|present|could not|couldn't|unable)\b"
    r"|\b(?:error|errors)\b.{0,80}\b(?:remain|remaining|still|unresolved|not fixed|not resolved|persist|present)\b"
    r"|\b(?:still|unresolved|remaining|persistent)\b.{0,80}\b(?:error|errors)\b"
    r"|не удалось|не смог|не смогл|не проверен|не удалось проверить|не прошло|не пройден|падает|упал|сбой|заблокирован"
    r"|ошибк.{0,80}(?:остал|сохраня|не исправ|не устран|присутств|есть|пока|сбой)"
    r"|(?:остал|сохраня|присутств|есть).{0,80}ошибк"
    r")",
    re.IGNORECASE,
)

# Strong keys are considered shell/process exit evidence in tool_response.
# Weak keys are accepted only in transcript exec_command_end records or objects
# that clearly look like a process result. This avoids treating application JSON
# such as {"status": 404} or {"code": 1} as a shell failure.
STRONG_EXIT_CODE_KEYS = (
    "exit_code",
    "exitCode",
    "returncode",
    "return_code",
    "returnCode",
)
WEAK_EXIT_CODE_KEYS = (
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
TOOL_NAME_KEYS = ("tool_name", "toolName", "tool", "name")

PROVIDER_ERROR_PATTERN = re.compile(
    r"(?:provider[_ -]?error|api[_ -]?error|rate[_ -]?limit|context[_ -]?overflow|max[_ -]?tokens|overloaded|gateway|network[_ -]?error|authentication|credential|request[_ -]?timeout|connection[_ -]?timeout)",
    re.IGNORECASE,
)
PROVIDER_ERROR_KEYS = ("error", "errors", "exception", "provider_error", "runtime_error", "api_error", "stopReason", "stop_reason")

SHELL_TOOL_NAMES = {"bash", "shell", "sh", "exec", "unified_exec", "terminal", "powershell", "pwsh", "cmd"}


@dataclass(frozen=True)
class ExitCodeEvidence:
    exit_code: Optional[int]
    source: str


@dataclass(frozen=True)
class CommandRisk:
    severity: str  # "deny" or "warn"
    code: str
    reason: str


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
        return {"_unison_error": "invalid_json"}


def _walk_key_values(value: Any) -> Iterable[Tuple[Optional[str], Any]]:
    if isinstance(value, dict):
        for key, child in value.items():
            yield str(key), child
            yield from _walk_key_values(child)
    elif isinstance(value, list):
        for child in value:
            yield None, child
            yield from _walk_key_values(child)


def _stringify_for_provider_scan(value: Any) -> str:
    if isinstance(value, str):
        return value[:2000]
    try:
        return json.dumps(value, ensure_ascii=False)[:2000]
    except Exception:
        return str(value)[:2000]


def event_indicates_provider_issue(event: Dict[str, Any]) -> bool:
    """Return True for provider/runtime failures without scanning assistant text.

    The v2 hook scanned the whole Stop event, which could skip false-success
    enforcement when the assistant merely mentioned words like "timeout". v3
    limits this bypass to explicit error-like fields.
    """
    if not isinstance(event, dict):
        return False
    for key, child in _walk_key_values(event):
        if key is None:
            continue
        key_norm = key.replace("-", "_").lower()
        if key_norm in {k.lower() for k in PROVIDER_ERROR_KEYS} or key_norm.endswith("_error") or key_norm.endswith("_exception"):
            if PROVIDER_ERROR_PATTERN.search(_stringify_for_provider_scan(child)):
                return True
    return False


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


def event_tool_name(event: Dict[str, Any]) -> str:
    for key in TOOL_NAME_KEYS:
        value = event.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return ""


def command_from_event(event: Dict[str, Any]) -> str:
    tool_input = event.get("tool_input")
    if isinstance(tool_input, dict):
        for key in ("command", "cmd", "script"):
            value = tool_input.get(key)
            if isinstance(value, str):
                return value.strip()
    return ""


def is_shell_tool_event(event: Dict[str, Any]) -> bool:
    name = event_tool_name(event).lower()
    if name:
        return name in SHELL_TOOL_NAMES or name == "bash"
    # Older/experimental Codex hook payloads sometimes omitted tool_name while
    # still using Bash-shaped tool_input. Treat that as shell only when a command
    # string is present, rather than classifying arbitrary MCP/apply_patch events.
    return bool(command_from_event(event))


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


def _looks_like_process_result(value: Dict[str, Any]) -> bool:
    keys = {str(k).lower() for k in value.keys()}
    return bool(keys & {"stdout", "stderr", "command", "cmd", "duration_ms", "duration", "pid", "signal", "exit_status", "exitcode"})


def _extract_exit_code_from_obj(value: Any, *, allow_weak: bool = False) -> Optional[int]:
    if isinstance(value, dict):
        for key in STRONG_EXIT_CODE_KEYS:
            if key in value:
                coerced = _coerce_int(value.get(key))
                if coerced is not None:
                    return coerced
        if allow_weak and _looks_like_process_result(value):
            for key in WEAK_EXIT_CODE_KEYS:
                if key in value:
                    coerced = _coerce_int(value.get(key))
                    if coerced is not None:
                        return coerced
    for child in _walk_values(value):
        if isinstance(child, dict):
            for key in STRONG_EXIT_CODE_KEYS:
                if key in child:
                    coerced = _coerce_int(child.get(key))
                    if coerced is not None:
                        return coerced
            if allow_weak and _looks_like_process_result(child):
                for key in WEAK_EXIT_CODE_KEYS:
                    if key in child:
                        coerced = _coerce_int(child.get(key))
                        if coerced is not None:
                            return coerced
    return None


def extract_exit_code(tool_response: Any) -> Optional[int]:
    return _extract_exit_code_from_obj(tool_response_payload(tool_response), allow_weak=False)


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
        if tool_use_id not in line:
            continue
        if "exec_command_end" not in line and not any(key in line for key in (*STRONG_EXIT_CODE_KEYS, *WEAK_EXIT_CODE_KEYS)):
            continue
        try:
            event = json.loads(line)
        except Exception:
            continue
        if not _contains_tool_use_id(event, tool_use_id):
            continue
        if not _contains_event_type(event, "exec_command_end"):
            continue
        exit_code = _extract_exit_code_from_obj(event, allow_weak=True)
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
    """Shallow shell segment splitter that respects quotes.

    This is still a classifier, not a full shell parser. It avoids v2's biggest
    pitfall: splitting or matching dangerous words inside quoted grep/echo docs.
    """
    segments: List[str] = []
    buf: List[str] = []
    quote: Optional[str] = None
    escape = False
    i = 0
    while i < len(command):
        ch = command[i]
        if escape:
            buf.append(ch)
            escape = False
            i += 1
            continue
        if ch == "\\" and quote != "'":
            buf.append(ch)
            escape = True
            i += 1
            continue
        if quote:
            buf.append(ch)
            if ch == quote:
                quote = None
            i += 1
            continue
        if ch in {"'", '"'}:
            quote = ch
            buf.append(ch)
            i += 1
            continue
        if ch == "\n" or ch == ";":
            segment = "".join(buf).strip()
            if segment:
                segments.append(segment)
            buf = []
            i += 1
            continue
        if command.startswith("&&", i) or command.startswith("||", i):
            segment = "".join(buf).strip()
            if segment:
                segments.append(segment)
            buf = []
            i += 2
            continue
        if ch == "|":
            segment = "".join(buf).strip()
            if segment:
                segments.append(segment)
            buf = []
            i += 1
            continue
        buf.append(ch)
        i += 1
    segment = "".join(buf).strip()
    if segment:
        segments.append(segment)
    return segments


def _tokenize(segment: str) -> List[str]:
    try:
        # Hook command payloads are shell strings even when the verifier runs on
        # Windows. POSIX tokenization keeps bash -lc wrappers inspectable; later
        # path normalization still handles Windows-style backslashes.
        return shlex.split(segment, posix=True)
    except Exception:
        return segment.strip().split()


def _command_basename(token: str) -> str:
    token = token.strip().strip('"\'')
    token = re.split(r"[/\\]+", token)[-1]
    lower = token.lower()
    for suffix in (".exe", ".cmd", ".bat", ".ps1"):
        if lower.endswith(suffix):
            lower = lower[: -len(suffix)]
            break
    return lower


def _strip_leading_options(tokens: List[str], options_with_values: Iterable[str]) -> List[str]:
    options_with_values = {opt.lower() for opt in options_with_values}
    out = list(tokens)
    while out and out[0].startswith("-") and out[0] != "-":
        opt = out.pop(0)
        key = opt.split("=", 1)[0].lower()
        if key in options_with_values and "=" not in opt and out:
            out.pop(0)
    return out


def _strip_env_assignments(tokens: Sequence[str]) -> List[str]:
    out = list(tokens)
    while out and re.match(r"^[A-Za-z_][A-Za-z0-9_]*=", out[0]):
        out.pop(0)
    if out and _command_basename(out[0]) == "env":
        out.pop(0)
        while out:
            if re.match(r"^[A-Za-z_][A-Za-z0-9_]*=", out[0]):
                out.pop(0)
                continue
            if out[0] in {"-i", "--ignore-environment"}:
                out.pop(0)
                continue
            if out[0] in {"-u", "--unset"}:
                out.pop(0)
                if out:
                    out.pop(0)
                continue
            if out[0].startswith("-"):
                out.pop(0)
                continue
            break
    if out and _command_basename(out[0]) in {"sudo", "doas"}:
        out.pop(0)
        out = _strip_leading_options(out, {"-u", "--user", "-g", "--group", "-h", "--host", "-p", "--prompt", "-C", "--close-from"})
    return out


def _strip_common_command_wrappers(tokens: Sequence[str]) -> List[str]:
    """Peel off common wrappers that do not change the inner command.

    This is not a security parser. It catches ordinary shell idioms such as
    `command rm -rf /`, `timeout 5 rm -rf /`, and `git -C repo clean -fdx`
    without matching dangerous words inside quoted documentation/search terms.
    """
    out = list(tokens)
    changed = True
    while changed and out:
        changed = False
        cmd = _command_basename(out[0])
        if cmd in {"command", "builtin"}:
            out.pop(0)
            if out and out[0] == "--":
                out.pop(0)
            changed = True
            continue
        if cmd in {"time", "nohup"}:
            out.pop(0)
            changed = True
            continue
        if cmd == "timeout":
            out.pop(0)
            while out and out[0].startswith("-") and out[0] != "-":
                opt = out.pop(0)
                if opt in {"-s", "--signal", "-k", "--kill-after"} and out:
                    out.pop(0)
            if out and re.fullmatch(r"\d+(?:\.\d+)?[smhd]?", out[0], re.IGNORECASE):
                out.pop(0)
            changed = True
            continue
        if cmd == "nice":
            out.pop(0)
            while out and out[0].startswith("-") and out[0] != "-":
                opt = out.pop(0)
                if opt in {"-n", "--adjustment"} and out:
                    out.pop(0)
            changed = True
            continue
    return out


def _git_subcommand_args(tokens: Sequence[str]) -> List[str]:
    """Return git args beginning with the subcommand, skipping global opts."""
    args = list(tokens[1:])
    while args:
        arg = args[0]
        if arg == "--":
            return args[1:]
        if arg in {"-C", "-c", "--config-env", "--git-dir", "--work-tree", "--namespace"}:
            args = args[2:] if len(args) >= 2 else []
            continue
        if arg.startswith("-C") and arg != "-C":
            args = args[1:]
            continue
        if arg.startswith("-c") and arg != "-c":
            args = args[1:]
            continue
        if arg.startswith(("--git-dir=", "--work-tree=", "--namespace=", "--config-env=")):
            args = args[1:]
            continue
        if arg.startswith("-"):
            args = args[1:]
            continue
        break
    return [a.lower() for a in args]


def _git_push_has_force(args: Sequence[str]) -> bool:
    for arg in args:
        if arg in {"--force", "-f"} or arg.startswith("--force=") or arg.startswith("--force-with-lease"):
            return True
        if arg.startswith("-") and not arg.startswith("--") and "f" in arg[1:]:
            return True
        if arg.startswith("+"):
            return True
    return False


def _runner_inner_tokens(tokens: Sequence[str]) -> Optional[List[str]]:
    tokens = list(tokens)
    if not tokens:
        return None
    cmd = _command_basename(tokens[0])
    args = list(tokens[1:])
    if cmd in {"uv", "poetry", "pipenv"} and args[:1] == ["run"]:
        inner = args[1:]
        options_with_values = {"--project", "--directory", "--python", "--with", "--with-editable", "--env-file", "-p"}
        while inner and inner[0].startswith("-") and inner[0] != "-":
            opt = inner.pop(0)
            key = opt.split("=", 1)[0]
            if key in options_with_values and "=" not in opt and inner:
                inner.pop(0)
        if inner and inner[0] == "--":
            inner = inner[1:]
        return inner or None
    if cmd == "npx":
        inner = list(args)
        while inner and inner[0].startswith("-"):
            # npx options can take values; for classification, skipping the option
            # token is enough for common verifier commands such as npx vitest.
            opt = inner.pop(0)
            if opt in {"-p", "--package", "-c", "--call"} and inner:
                if opt in {"-c", "--call"}:
                    return _tokenize(inner[0])
                inner.pop(0)
        return inner or None
    if cmd in {"npm", "pnpm", "yarn"} and args[:1] == ["exec"]:
        inner = args[1:]
        if inner and inner[0] == "--":
            inner = inner[1:]
        return inner or None
    return None


def _shell_inner_command(tokens: Sequence[str]) -> Optional[str]:
    if not tokens:
        return None
    cmd = _command_basename(tokens[0])
    args = list(tokens[1:])
    if cmd in {"bash", "sh", "zsh", "dash", "ksh", "fish"}:
        for idx, arg in enumerate(args):
            if arg == "--":
                continue
            if arg == "-c" or (arg.startswith("-") and "c" in arg and not arg.startswith("--")):
                if idx + 1 < len(args):
                    next_idx = idx + 1
                    if args[next_idx] == "--" and next_idx + 1 < len(args):
                        next_idx += 1
                    return args[next_idx]
        return None
    if cmd in {"cmd"}:
        for idx, arg in enumerate(args):
            if arg.lower() in {"/c", "-c"} and idx + 1 < len(args):
                return args[idx + 1]
        return None
    if cmd in {"powershell", "pwsh"}:
        for idx, arg in enumerate(args):
            if arg.lower() in {"-command", "-c", "/c"} and idx + 1 < len(args):
                return args[idx + 1]
        return None
    return None


def _find_matching_dollar_paren(text: str, start: int) -> Optional[int]:
    """Return the closing paren for a `$(` command substitution.

    The classifier is intentionally shallow, but command substitution is a real
    execution boundary. Without this scan, `echo $(rm -rf /)` is tokenized as an
    `echo` command and the destructive inner command is invisible to preflight.
    """
    depth = 0
    quote: Optional[str] = None
    escape = False
    i = start
    while i < len(text):
        ch = text[i]
        if escape:
            escape = False
            i += 1
            continue
        if ch == "\\" and quote != "'":
            escape = True
            i += 1
            continue
        if quote:
            if ch == quote:
                quote = None
            i += 1
            continue
        if ch in {"'", '"'}:
            quote = ch
            i += 1
            continue
        if text.startswith("$(", i):
            depth += 1
            i += 2
            continue
        if ch == ")":
            depth -= 1
            if depth == 0:
                return i
        i += 1
    return None


def _extract_executable_subcommands(text: str) -> List[str]:
    """Extract shell command substitutions that execute outside single quotes."""
    subcommands: List[str] = []
    quote: Optional[str] = None
    escape = False
    i = 0
    while i < len(text):
        ch = text[i]
        if escape:
            escape = False
            i += 1
            continue
        if ch == "\\" and quote != "'":
            escape = True
            i += 1
            continue
        if quote == "'":
            if ch == "'":
                quote = None
            i += 1
            continue
        if ch == "'" and quote is None:
            quote = "'"
            i += 1
            continue
        if ch == '"':
            quote = None if quote == '"' else '"'
            i += 1
            continue
        if text.startswith("$(", i):
            end = _find_matching_dollar_paren(text, i)
            if end is None:
                i += 2
                continue
            inner = text[i + 2 : end].strip()
            if inner:
                subcommands.append(inner)
            i = end + 1
            continue
        if ch == "`":
            j = i + 1
            inner: List[str] = []
            escaped = False
            while j < len(text):
                cj = text[j]
                if escaped:
                    inner.append(cj)
                    escaped = False
                    j += 1
                    continue
                if cj == "\\":
                    escaped = True
                    j += 1
                    continue
                if cj == "`":
                    candidate = "".join(inner).strip()
                    if candidate:
                        subcommands.append(candidate)
                    i = j + 1
                    break
                inner.append(cj)
                j += 1
            else:
                i += 1
            continue
        i += 1
    return subcommands


def _segments_tokens(command: str, *, _depth: int = 0) -> Iterable[List[str]]:
    if _depth > 3:
        return
    for segment in _split_command_segments(command):
        tokens = _strip_common_command_wrappers(_strip_env_assignments(_tokenize(segment)))
        if not tokens:
            continue
        yield tokens
        inner = _shell_inner_command(tokens)
        if inner:
            yield from _segments_tokens(inner, _depth=_depth + 1)
            continue
        runner = _runner_inner_tokens(tokens)
        if runner:
            yield runner
        for subcommand in _extract_executable_subcommands(segment):
            yield from _segments_tokens(subcommand, _depth=_depth + 1)


def command_expected_nonzero(command: str, exit_code: Optional[int] = None) -> bool:
    if exit_code != 1:
        return False
    for tokens in _segments_tokens(command):
        cmd = _command_basename(tokens[0])
        args = [t.lower() for t in tokens[1:]]
        if cmd in {"grep", "egrep", "fgrep", "rg", "ripgrep", "findstr", "select-string"}:
            return True
        if cmd in {"which", "where", "pgrep"}:
            return True
        if cmd == "command" and args[:1] == ["-v"]:
            return True
        if cmd == "type" and any(a in {"-p", "-path"} for a in args):
            return True
        if cmd in {"test", "[", "[["}:
            return True
        if cmd == "cmp" and (not args or any(a in {"-s", "--silent", "--quiet"} for a in args)):
            return True
        if cmd == "git":
            git_args = _git_subcommand_args(tokens)
            if git_args[:1] == ["grep"]:
                return True
            if git_args[:1] == ["diff"] and any(a in {"--quiet", "-q", "--exit-code"} for a in git_args):
                return True
        if cmd == "diff" and any(a in {"--quiet", "-q", "--brief"} for a in args):
            return True
    return False


def _has_script_name(args: Sequence[str], names: Iterable[str]) -> bool:
    wanted = {name.lower() for name in names}
    for arg in args:
        normalized = Path(arg.strip('"\'')).name.lower().replace("_", "-")
        if normalized in wanted:
            return True
    return False


def _python_invocation_is_verification(args: Sequence[str]) -> bool:
    args_l = [a.lower() for a in args]
    if "-m" in args_l:
        idx = args_l.index("-m")
        module = args_l[idx + 1] if idx + 1 < len(args_l) else ""
        if module in {"pytest", "unittest", "mypy", "py_compile", "compileall", "ruff", "flake8"}:
            return True
    script_names = {"verify-bundle.py", "verify_bundle.py", "run-fixtures.py", "run_fixtures.py", "run-tool-fixtures.py", "run_tool_fixtures.py", "run-installer-fixtures.py", "run_installer_fixtures.py"}
    if _has_script_name(args, script_names):
        return True
    for idx, arg in enumerate(args_l):
        if Path(arg).name == "manage.py" and "test" in args_l[idx + 1 : idx + 3]:
            return True
    return False


def command_is_verification(command: str) -> bool:
    """Conservative verification detector.

    v3 recognizes project verifier scripts and common runners while avoiding broad
    substrings like any occurrence of "build" in an arbitrary command.
    """
    verification_commands = {"pytest", "py.test", "jest", "vitest", "rspec", "phpunit", "eslint", "stylelint", "shellcheck", "flake8", "mypy", "pyright", "ruff", "biome", "tsc"}
    verification_scripts = {"verify-bundle.py", "verify_bundle.py", "run-fixtures.py", "run_fixtures.py", "test.sh", "check.sh", "verify.sh"}
    for tokens in _segments_tokens(command):
        cmd = _command_basename(tokens[0])
        args = [a.lower() for a in tokens[1:]]

        if cmd in verification_commands:
            return True
        if cmd in verification_scripts:
            return True
        if cmd in {"npm", "pnpm", "yarn"}:
            if args[:1] in (["test"], ["build"], ["lint"]):
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
        if cmd in {"python", "python3", "py"} and _python_invocation_is_verification(tokens[1:]):
            return True
        if _has_script_name(tokens, verification_scripts):
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
    return ensure_guard_dir(repo_root) / "unison_turn_state.v3.json"


def legacy_turn_state_path(repo_root: Path) -> Path:
    return ensure_guard_dir(repo_root) / "unison_turn_state.v2.json"


def seed_turn_state(turn_id: str) -> Dict[str, Any]:
    return {
        "schema": TURN_STATE_SCHEMA,
        "package_version": PACKAGE_VERSION,
        "turn_id": turn_id,
        "command_seq": 0,
        "commands": [],
        "failure_count": 0,
        "last_failure_seq": None,
        "last_successful_verification_seq": None,
        "stop_block_count": 0,
    }


def _upgrade_v2_state(state: Dict[str, Any], turn_id: str) -> Dict[str, Any]:
    commands = state.get("commands") if isinstance(state.get("commands"), list) else []
    upgraded = seed_turn_state(turn_id)
    upgraded["commands"] = []
    for idx, record in enumerate(commands, start=1):
        if isinstance(record, dict):
            new_record = dict(record)
            new_record.setdefault("seq", idx)
            upgraded["commands"].append(new_record)
    upgraded["command_seq"] = len(upgraded["commands"])
    upgraded["failure_count"] = int(state.get("failure_count") or 0)
    last_failure_index = state.get("last_failure_index")
    if isinstance(last_failure_index, int) and 0 <= last_failure_index < len(upgraded["commands"]):
        upgraded["last_failure_seq"] = upgraded["commands"][last_failure_index].get("seq")
    else:
        failures = [r for r in upgraded["commands"] if isinstance(r, dict) and r.get("failed")]
        if failures:
            upgraded["last_failure_seq"] = failures[-1].get("seq")
    last_success_index = state.get("last_successful_verification_index")
    if isinstance(last_success_index, int) and 0 <= last_success_index < len(upgraded["commands"]):
        upgraded["last_successful_verification_seq"] = upgraded["commands"][last_success_index].get("seq")
    else:
        successes = [r for r in upgraded["commands"] if isinstance(r, dict) and r.get("is_verification") and r.get("exit_code") == 0]
        if successes:
            upgraded["last_successful_verification_seq"] = successes[-1].get("seq")
    upgraded["stop_block_count"] = int(state.get("stop_block_count") or 0)
    return upgraded


def load_turn_state(repo_root: Path, turn_id: str) -> Dict[str, Any]:
    state = load_json(turn_state_path(repo_root), {})
    if not isinstance(state, dict) or state.get("turn_id") != turn_id:
        legacy = load_json(legacy_turn_state_path(repo_root), {})
        if isinstance(legacy, dict) and legacy.get("turn_id") == turn_id:
            return _upgrade_v2_state(legacy, turn_id)
        return seed_turn_state(turn_id)
    state.setdefault("schema", TURN_STATE_SCHEMA)
    state.setdefault("package_version", PACKAGE_VERSION)
    state.setdefault("command_seq", len(state.get("commands") or []))
    state.setdefault("commands", [])
    state.setdefault("failure_count", 0)
    state.setdefault("last_failure_seq", None)
    state.setdefault("last_successful_verification_seq", None)
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
    seq = int(state.get("command_seq") or 0) + 1
    state["command_seq"] = seq
    record = {
        "seq": seq,
        "command": command,
        "is_verification": is_verification,
        "failed": failed,
        "exit_code": evidence.exit_code,
        "exit_code_source": evidence.source,
        "expected_nonzero": expected_nonzero,
        "summary": summarize_text(text),
    }
    state["commands"] = (state.get("commands") or [])[-(MAX_COMMAND_LOG - 1) :] + [record]
    if failed:
        state["failure_count"] = int(state.get("failure_count") or 0) + 1
        state["last_failure_seq"] = seq
    elif is_verification and evidence.exit_code == 0:
        state["last_successful_verification_seq"] = seq
    write_turn_state(repo_root, state)
    return state


def _as_int_or_none(value: Any) -> Optional[int]:
    try:
        return int(value) if value is not None else None
    except Exception:
        return None


def unresolved_turn_failure(state: Dict[str, Any]) -> bool:
    last_failure_seq = _as_int_or_none(state.get("last_failure_seq"))
    if last_failure_seq is None:
        return False
    last_success_seq = _as_int_or_none(state.get("last_successful_verification_seq"))
    return last_success_seq is None or last_success_seq < last_failure_seq


def latest_failure(state: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    commands = state.get("commands") or []
    last_failure_seq = _as_int_or_none(state.get("last_failure_seq"))
    if last_failure_seq is not None:
        for value in reversed(commands):
            if isinstance(value, dict) and _as_int_or_none(value.get("seq")) == last_failure_seq:
                return value
    for value in reversed(commands):
        if isinstance(value, dict) and value.get("failed"):
            return value
    return None


def increment_stop_block_count(repo_root: Path, state: Dict[str, Any]) -> Dict[str, Any]:
    state["stop_block_count"] = int(state.get("stop_block_count") or 0) + 1
    write_turn_state(repo_root, state)
    return state


def _target_is_broad_or_system_path(target: str) -> bool:
    t = target.strip().strip('"\'')
    if not t:
        return False
    raw_lower = _canonical_target_lower(t)
    if raw_lower in {
        "/",
        "/*",
        "~",
        "~/",
        "~\\",
        "~/*",
        "~\\*",
        "$home",
        "${home}",
        "$env:home",
        "$env:userprofile",
        "${env:home}",
        "${env:userprofile}",
        "%userprofile%",
        "%homepath%",
    }:
        return True
    t_lower = raw_lower.rstrip("/\\") or raw_lower
    if re.fullmatch(r"[a-z]:", t_lower) or re.fullmatch(r"[a-z]:[/\\]?", t_lower) or re.fullmatch(r"[a-z]:[/\\]\*", t_lower):
        return True
    system_roots = (
        "/bin", "/sbin", "/usr", "/etc", "/var", "/opt", "/lib", "/lib64", "/boot", "/dev", "/proc", "/sys", "/root",
        "/applications", "/system", "/library", "c:/windows", "c:\\windows", "c:/program files", "c:\\program files",
    )
    if any(t_lower == root or t_lower.startswith(root + "/") or t_lower.startswith(root + "\\") for root in system_roots):
        return True

    # Home roots are destructive at the root/user-home level, but a scoped path
    # under a project directory should be a warning, not a hard deny. This avoids
    # blocking legitimate cleanups such as `rm -rf /home/alice/project/build`.
    normalized = t_lower.replace("\\", "/").strip("/")
    parts = [part for part in normalized.split("/") if part and part != "*"]
    if parts[:1] in (["home"], ["users"]):
        return len(parts) <= 2
    if len(parts) >= 2 and re.fullmatch(r"[a-z]:", parts[0]) and parts[1] == "users":
        return len(parts) <= 3
    return False


def _target_is_repo_metadata(target: str) -> bool:
    parts = re.split(r"[/\\]+", target.strip().strip('"\''))
    return any(part == ".git" for part in parts)


def _canonical_target_lower(target: str) -> str:
    r"""Normalize paths for policy checks after shell tokenization.

    On POSIX, shlex treats backslashes as escapes, so a Windows path typed as
    `C:\Users\Alice` can arrive as `C:UsersAlice`. Recognize common absolute
    Windows roots after this loss so the guard still catches broad deletes in
    cross-platform fixture/runtime payloads.
    """
    raw = target.strip().strip('"\'').lower().replace("\\", "/").replace("//", "/")
    if raw.startswith("c:users") and not raw.startswith("c:/users"):
        return "c:/users/" + raw[len("c:users") :].lstrip("/")
    for root in ("windows", "program files", "programdata"):
        prefix = "c:" + root
        if raw.startswith(prefix) and not raw.startswith("c:/"):
            return "c:/" + raw[2:]
    return raw


def _rm_flags_and_targets(tokens: Sequence[str]) -> Tuple[bool, bool, List[str]]:
    recursive = False
    force = False
    targets: List[str] = []
    parsing_options = True
    for token in list(tokens)[1:]:
        if parsing_options and token == "--":
            parsing_options = False
            continue
        if parsing_options and token.startswith("--"):
            if token == "--recursive":
                recursive = True
                continue
            if token == "--force":
                force = True
                continue
            if token == "--no-preserve-root":
                continue
            # Unknown long rm option: treat as option, not target.
            continue
        if parsing_options and token.startswith("-") and token != "-":
            flags = token[1:]
            if "r" in flags or "R" in flags:
                recursive = True
            if "f" in flags:
                force = True
            continue
        targets.append(token)
    return recursive, force, targets


def _powershell_remove_flags_and_targets(tokens: Sequence[str]) -> Tuple[bool, bool, List[str]]:
    recursive = False
    force = False
    targets: List[str] = []
    args = list(tokens)[1:]
    idx = 0
    path_options = {"-path", "-literalpath"}
    value_options = path_options | {"-filter", "-include", "-exclude", "-credential", "-stream"}
    while idx < len(args):
        token = args[idx]
        lower = token.lower()
        if lower in {"-recurse", "-recursive", "-r"}:
            recursive = True
            idx += 1
            continue
        if lower in {"-force", "-f"}:
            force = True
            idx += 1
            continue
        if lower in path_options and idx + 1 < len(args):
            targets.append(args[idx + 1])
            idx += 2
            continue
        if lower in value_options:
            idx += 2 if idx + 1 < len(args) else 1
            continue
        matched_path = False
        for option in path_options:
            if lower.startswith(option + ":"):
                value = token.split(":", 1)[1]
                if value:
                    targets.append(value)
                matched_path = True
                break
        if matched_path:
            idx += 1
            continue
        if lower.startswith("-"):
            idx += 1
            continue
        targets.append(token)
        idx += 1
    return recursive, force, targets


def _cmd_remove_flags_and_targets(tokens: Sequence[str]) -> Tuple[bool, bool, List[str]]:
    recursive = False
    force = False
    targets: List[str] = []
    for token in list(tokens)[1:]:
        lower = token.lower()
        if lower.startswith("/"):
            if "s" in lower[1:]:
                recursive = True
            if "q" in lower[1:] or "f" in lower[1:]:
                force = True
            continue
        targets.append(token)
    return recursive, force, targets


def _target_is_absolute_or_home(target: str) -> bool:
    stripped = target.strip().strip('"\'')
    canonical = _canonical_target_lower(stripped)
    return bool(stripped.startswith(("/", "~")) or re.match(r"^[a-z]:/", canonical) or canonical.startswith(("$home", "${home}", "$env:", "%userprofile%", "%homepath%")))


def _target_is_raw_device(target: str) -> bool:
    t = _canonical_target_lower(target)
    return bool(
        re.match(r"^/dev/(?:sd[a-z]\d*|vd[a-z]\d*|xvd[a-z]\d*|hd[a-z]\d*|nvme\d+n\d+(?:p\d+)?|disk\d+|rdisk\d+)", t)
        or t.startswith("//./physicaldrive")
        or t.startswith("/./physicaldrive")
        # POSIX shlex can collapse `\\.\PhysicalDrive0` into
        # `\.PhysicalDrive0`; still treat that as a raw Windows disk.
        or re.search(r"(?:^|[./])physicaldrive\d+$", t)
        or re.match(r"^[a-z]:$", t)
    )


def _redirection_targets(tokens: Sequence[str]) -> List[str]:
    targets: List[str] = []
    args = list(tokens)
    idx = 0
    while idx < len(args):
        token = args[idx]
        if token in {">", ">>", "1>", "1>>", "2>", "2>>", "&>", "&>>"}:
            if idx + 1 < len(args):
                targets.append(args[idx + 1])
                idx += 2
                continue
        match = re.match(r"^(?:[12]?>>?|&>>?)(.+)$", token)
        if match and match.group(1):
            targets.append(match.group(1))
        idx += 1
    return targets


def _segment_tokens_for_pipeline_scan(command: str) -> List[List[str]]:
    segments: List[List[str]] = []
    for segment in _split_command_segments(command):
        tokens = _strip_common_command_wrappers(_strip_env_assignments(_tokenize(segment)))
        if tokens:
            segments.append(tokens)
    return segments


def _pipeline_remote_script_warning(command: str) -> Optional[CommandRisk]:
    segments = _segment_tokens_for_pipeline_scan(command)
    if len(segments) < 2:
        return None
    download_seen = False
    for tokens in segments:
        cmd = _command_basename(tokens[0])
        args = [a.lower() for a in tokens[1:]]
        if cmd in {"curl", "wget", "fetch", "iwr", "irm", "invoke-webrequest", "invoke-restmethod"}:
            download_seen = True
            continue
        if download_seen and cmd in {"sh", "bash", "zsh", "dash", "ksh", "fish", "powershell", "pwsh", "python", "python3", "ruby", "perl", "node"}:
            return CommandRisk("warn", "remote_download_piped_to_interpreter", "Remote download piped to an interpreter detected; verify source trust and user intent before relying on it.")
        if cmd not in {"tee", "cat", "sed", "awk", "grep", "rg", "head", "tail"} and not args:
            download_seen = False
    return None


def _append_delete_risks(risks: List[CommandRisk], *, recursive: bool, force: bool, targets: Sequence[str], system_code: str, metadata_code: str, absolute_code: str, command_label: str) -> None:
    if recursive and force and any(_target_is_broad_or_system_path(t) for t in targets):
        risks.append(CommandRisk("deny", system_code, f"Refusing recursive forced delete of a broad system/home/root path via {command_label}."))
        return
    if recursive and any(_target_is_repo_metadata(t) for t in targets):
        risks.append(CommandRisk("deny", metadata_code, f"Refusing recursive delete of repository metadata such as .git via {command_label}."))
        return
    if recursive and force and targets and any(_target_is_absolute_or_home(str(t)) for t in targets):
        risks.append(CommandRisk("warn", absolute_code, f"Recursive forced delete of an absolute/home path via {command_label}; verify the target is intentional and scoped."))


def classify_command_risks(command: str, repo_root: Optional[Path] = None) -> List[CommandRisk]:
    risks: List[CommandRisk] = []
    pipeline_risk = _pipeline_remote_script_warning(command)
    if pipeline_risk is not None:
        risks.append(pipeline_risk)
    for tokens in _segments_tokens(command):
        if not tokens:
            continue
        cmd = _command_basename(tokens[0])
        args = [a.lower() for a in tokens[1:]]
        for target in _redirection_targets(tokens):
            if _target_is_raw_device(target):
                risks.append(CommandRisk("deny", "redirect_raw_device", "Refusing shell redirection to a raw block device."))
                break
        if cmd == "rm":
            ps_recursive, ps_force, ps_targets = _powershell_remove_flags_and_targets(tokens)
            if ps_targets and ("-recurse" in args or "-recursive" in args or "-force" in args):
                _append_delete_risks(
                    risks,
                    recursive=ps_recursive,
                    force=ps_force,
                    targets=ps_targets,
                    system_code="powershell_rm_recursive_force_system_path",
                    metadata_code="powershell_rm_repo_metadata",
                    absolute_code="powershell_rm_recursive_force_absolute",
                    command_label="PowerShell rm alias",
                )
                continue
            recursive, force, targets = _rm_flags_and_targets(tokens)
            _append_delete_risks(
                risks,
                recursive=recursive,
                force=force,
                targets=targets,
                system_code="rm_recursive_force_system_path",
                metadata_code="rm_repo_metadata",
                absolute_code="rm_recursive_force_absolute",
                command_label="rm",
            )
            continue
        if cmd in {"remove-item", "ri"}:
            recursive, force, targets = _powershell_remove_flags_and_targets(tokens)
            _append_delete_risks(
                risks,
                recursive=recursive,
                force=force,
                targets=targets,
                system_code="powershell_remove_item_recursive_force_system_path",
                metadata_code="powershell_remove_item_repo_metadata",
                absolute_code="powershell_remove_item_recursive_force_absolute",
                command_label="Remove-Item",
            )
            continue
        if cmd in {"rd", "rmdir", "del", "erase"}:
            recursive, force, targets = _cmd_remove_flags_and_targets(tokens)
            _append_delete_risks(
                risks,
                recursive=recursive,
                force=force,
                targets=targets,
                system_code="cmd_recursive_force_system_path",
                metadata_code="cmd_repo_metadata",
                absolute_code="cmd_recursive_force_absolute",
                command_label=cmd,
            )
            continue
        if cmd == "git":
            git_args = _git_subcommand_args(tokens)
            if git_args[:2] == ["reset", "--hard"]:
                risks.append(CommandRisk("warn", "git_reset_hard", "git reset --hard rewrites the working tree; proceed only with explicit user intent."))
                continue
            if git_args[:1] == ["clean"] and any(a.startswith("-") and "f" in a and "d" in a for a in git_args[1:]):
                risks.append(CommandRisk("warn", "git_clean_force", "git clean with force deletes untracked files; proceed only with explicit user intent."))
                continue
            if git_args[:1] == ["push"] and _git_push_has_force(git_args[1:]):
                risks.append(CommandRisk("deny", "git_force_push", "Refusing force-push from an automated turn; ask the user to run or explicitly approve shared-history rewrite."))
                continue
        if re.fullmatch(r"mkfs(?:\.[a-z0-9]+)?", cmd):
            risks.append(CommandRisk("deny", "mkfs", "Refusing filesystem formatting command."))
            continue
        if cmd == "dd":
            of_args = [a for a in tokens[1:] if a.startswith("of=")]
            if any(_target_is_raw_device(a.split("=", 1)[1]) for a in of_args if "=" in a):
                risks.append(CommandRisk("deny", "dd_raw_device", "Refusing raw destructive disk write command."))
            elif of_args:
                risks.append(CommandRisk("warn", "dd_output_file", "dd writes raw bytes; verify the output path before continuing."))
            continue
        if cmd == "tee" and any(_target_is_raw_device(a) for a in tokens[1:] if not a.startswith("-")):
            risks.append(CommandRisk("deny", "tee_raw_device", "Refusing tee write to a raw block device."))
            continue
        if cmd in {"chmod", "chown", "chgrp"} and any(a.lower().startswith("-r") or a.lower() == "--recursive" for a in tokens[1:]):
            targets = [a for a in tokens[1:] if not a.startswith("-")][1 if cmd == "chown" and len([a for a in tokens[1:] if not a.startswith("-")]) > 1 else 0 :]
            if any(_target_is_broad_or_system_path(t) for t in targets):
                risks.append(CommandRisk("deny", f"{cmd}_recursive_system_path", f"Refusing recursive {cmd} against a broad system/home/root path."))
                continue
        if cmd in {"shutdown", "reboot", "poweroff", "halt"}:
            risks.append(CommandRisk("deny", "power_control", "Refusing machine power control command."))
            continue
        if cmd in {"stop-computer", "restart-computer"}:
            risks.append(CommandRisk("deny", "powershell_power_control", "Refusing machine power control command."))
            continue
    return risks


def strongest_risk(risks: Sequence[CommandRisk]) -> Optional[CommandRisk]:
    for risk in risks:
        if risk.severity == "deny":
            return risk
    for risk in risks:
        if risk.severity == "warn":
            return risk
    return None


def json_print(data: Dict[str, Any]) -> None:
    print(json.dumps(data, ensure_ascii=False))


def safe_run(fn) -> int:
    try:
        return int(fn() or 0)
    except Exception:
        # Hooks are guardrails, not a reason to break the entire Codex turn.
        return 0
