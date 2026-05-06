#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

DEFAULT_ROOT = ".codex-hybrid/tool-results"
DEFAULT_PREVIEW_BYTES = 4096
MAX_LABEL_CHARS = 48


def _slug(value: str) -> str:
    value = (value or "tool-output").strip().lower()
    value = re.sub(r"[^a-z0-9._-]+", "-", value)
    value = re.sub(r"-+", "-", value).strip("-._")
    return (value or "tool-output")[:MAX_LABEL_CHARS]


def _read_input(path: Optional[str]) -> bytes:
    if path:
        return Path(path).read_bytes()
    return sys.stdin.buffer.read()


def _count_lines(data: bytes) -> int:
    if not data:
        return 0
    count = data.count(b"\n")
    return count if data.endswith(b"\n") else count + 1


def _safe_decode(data: bytes) -> str:
    return data.decode("utf-8", errors="replace")


def _preview(data: bytes, preview_bytes: int) -> Tuple[str, bool]:
    if preview_bytes < 0:
        preview_bytes = 0
    if len(data) <= preview_bytes:
        return _safe_decode(data), False
    sample = data[:preview_bytes]
    newline = sample.rfind(b"\n")
    if newline > preview_bytes // 2:
        sample = sample[:newline]
    return _safe_decode(sample), True


def _unique_path(root: Path, label: str, digest: str, ext: str = ".txt") -> Path:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    base = f"{stamp}-{_slug(label)}-{digest[:12]}"
    candidate = root / f"{base}{ext}"
    idx = 1
    while candidate.exists():
        candidate = root / f"{base}-{idx}{ext}"
        idx += 1
    return candidate


def persist_bytes(data: bytes, root: Path, label: str, preview_bytes: int = DEFAULT_PREVIEW_BYTES) -> Dict[str, Any]:
    root = root.expanduser().resolve()
    root.mkdir(parents=True, exist_ok=True)
    digest = hashlib.sha256(data).hexdigest()
    out_path = _unique_path(root, label, digest)
    out_path.write_bytes(data)
    preview, truncated = _preview(data, preview_bytes)
    meta = {
        "schema": "codex-claude-unison.tool-result.v1",
        "label": label,
        "path": str(out_path),
        "sha256": digest,
        "bytes": len(data),
        "lines": _count_lines(data),
        "preview_bytes": preview_bytes,
        "preview_truncated": truncated,
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
    }
    meta_path = out_path.with_suffix(out_path.suffix + ".json")
    meta_path.write_text(json.dumps(meta, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    meta["metadata_path"] = str(meta_path)
    meta["preview"] = preview
    return meta


def render_markdown(result: Dict[str, Any]) -> str:
    preview = str(result.get("preview") or "")
    suffix = "\n... preview truncated; reopen the path above for the full output." if result.get("preview_truncated") else ""
    return (
        "# Persisted tool result\n\n"
        f"- Full output: `{result['path']}`\n"
        f"- Metadata: `{result['metadata_path']}`\n"
        f"- Bytes: {result['bytes']}\n"
        f"- Lines: {result['lines']}\n"
        f"- SHA256: `{result['sha256']}`\n\n"
        "## Preview\n\n"
        "```text\n"
        f"{preview}{suffix}\n"
        "```\n"
    )


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Persist a large tool/command result and print a compact model-facing reference.")
    parser.add_argument("input", nargs="?", help="File to persist. If omitted, stdin is used.")
    parser.add_argument("--root", default=DEFAULT_ROOT, help="Directory for persisted outputs. Default: .codex-hybrid/tool-results")
    parser.add_argument("--label", default="tool-output", help="Short label used in the saved filename.")
    parser.add_argument("--preview-bytes", type=int, default=DEFAULT_PREVIEW_BYTES, help="Approximate bytes to include in the preview.")
    parser.add_argument("--json", action="store_true", help="Print JSON instead of markdown.")
    return parser.parse_args(argv)


def main(argv: list[str]) -> int:
    args = parse_args(argv)
    data = _read_input(args.input)
    result = persist_bytes(data, Path(args.root), args.label, args.preview_bytes)
    if args.json:
        print(json.dumps(result, indent=2, ensure_ascii=False))
    else:
        print(render_markdown(result))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
