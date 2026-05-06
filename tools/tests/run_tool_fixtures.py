#!/usr/bin/env python3
from __future__ import annotations

import importlib.util
import json
import tempfile
import unittest
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
PERSIST = ROOT / "tools" / "persist_tool_result.py"
DOCTOR = ROOT / "tools" / "context_doctor.py"


def load_module(path: Path, name: str) -> Any:
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise AssertionError(f"Could not load {path}")
    module = importlib.util.module_from_spec(spec)
    import sys as _sys
    _sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


persist = load_module(PERSIST, "persist_tool_result")
doctor = load_module(DOCTOR, "context_doctor")


class ToolFixtureTests(unittest.TestCase):
    def test_persist_tool_result_saves_full_output_and_preview(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td) / ".codex-hybrid" / "tool-results"
            data = ("Request failed is just output\n" * 300).encode()
            result = persist.persist_bytes(data, root, "npm-test", preview_bytes=80)
            path = Path(result["path"])
            self.assertTrue(path.exists())
            self.assertEqual(path.read_bytes(), data)
            self.assertTrue(Path(result["metadata_path"]).exists())
            self.assertLess(len(result["preview"]), len(data.decode()))
            self.assertTrue(result["preview_truncated"])

    def test_persist_tool_result_does_not_overwrite_same_content(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td) / "results"
            data = b"same output\n"
            first = persist.persist_bytes(data, root, "same")
            second = persist.persist_bytes(data, root, "same")
            self.assertNotEqual(first["path"], second["path"])
            self.assertTrue(Path(first["path"]).exists())
            self.assertTrue(Path(second["path"]).exists())

    def test_context_doctor_reports_large_artifacts_without_deleting(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            big = root / "debug.log"
            big.write_text("x" * 250_000, encoding="utf-8")
            report = doctor.build_report(root)
            self.assertGreaterEqual(report["finding_count"], 1)
            self.assertTrue(big.exists())
            categories = {item["category"] for item in report["findings"]}
            self.assertIn("large-log-or-artifact", categories)

    def test_context_doctor_detects_unresolved_failure_state(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            state_path = root / ".codex-hybrid" / "guard" / "unison_turn_state.v2.json"
            state_path.parent.mkdir(parents=True)
            state_path.write_text(json.dumps({"last_failure_index": 2, "last_successful_verification_index": 1}), encoding="utf-8")
            report = doctor.build_report(root)
            categories = {item["category"] for item in report["findings"]}
            self.assertIn("unresolved-shell-failure", categories)


if __name__ == "__main__":
    unittest.main(verbosity=2)
