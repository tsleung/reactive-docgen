#!/usr/bin/env python3
"""
RDG Engine Error-Visibility Regression Test.

WorkGraph: wo-task-rdg-engine-error-visibility (P2/I3)
ACC: ACC-engine-error-surfaced

Problem (pre-fix): when an LLM call failed (context overflow, API error, parse
failure, timeout, non-zero CLI exit) the engine swallowed the exception and
`return ""`. The caller then wrote a 0-byte output file; the runner printed
"✗ generation failed" but the ACTUAL cause (e.g. "context window exceeded")
was invisible — diagnosing required hand-reading the .rdg pipeline.

Required behavior (this test's contract): on ANY exception/failure from the
LLM call, `call_claude` must return a NON-EMPTY error sentinel of the form
``RDG-ENGINE-ERROR: <ExceptionType>: <message>`` so the caller writes a
non-empty error report carrying the cause (satisfies audit-rdg-empty-reports.ts
AND makes the failure visible).

STRICT SCOPE — only the EXCEPTION/failure path changes:
  - A genuinely-empty model response with NO exception still yields "".
  - No process-exit is used to signal the per-call failure.

Fix-First contract (red -> green): this suite asserts the NEW contract
(non-empty sentinel). The `test_revert_guard_*` cases document the OLD,
now-forbidden contract ("" on exception) so that reverting the fix turns them
red — they assert the engine does NOT return "" on the exception path.

This is a STRUCTURAL test — no real Claude call, no network, no credentials.
`subprocess.run` is mocked to raise / return a non-zero exit.

Exit codes:
  0  All tests pass.
  1  One or more tests failed.

Run (use the project venv — claude.py -> config.py imports python-dotenv):
  ./.venv/bin/python tests/test_engine_error_visibility.py
or, if python-dotenv is already on the active interpreter:
  python3 tests/test_engine_error_visibility.py
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest import mock

# Make the rdg package importable without installing the project (mirrors
# tests/test_switch.py). Importing rdg.claude directly is side-effect-free —
# it does NOT run the import-time exit(1) availability checks that rdg.gemini
# performs, so the test needs no claude CLI / GEMINI_API_KEY on PATH/in env.
TESTS_DIR = Path(__file__).resolve().parent
REACTIVE_DOCGEN_DIR = TESTS_DIR.parent
SRC_DIR = REACTIVE_DOCGEN_DIR / "src"

if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from rdg import claude as claude_module  # noqa: E402
from rdg.claude import (  # noqa: E402
    ENGINE_ERROR_SENTINEL,
    call_claude,
    format_engine_error,
)


# ─────────────────────────────────────────────────────────────────────────────
# format_engine_error — the sentinel builder
# ─────────────────────────────────────────────────────────────────────────────


class TestSentinelFormatter(unittest.TestCase):
    def test_sentinel_prefix_constant(self) -> None:
        self.assertEqual(ENGINE_ERROR_SENTINEL, "RDG-ENGINE-ERROR")

    def test_format_carries_type_and_message(self) -> None:
        s = format_engine_error("RuntimeError", "context window exceeded")
        self.assertTrue(s.startswith("RDG-ENGINE-ERROR:"))
        self.assertIn("RuntimeError", s)
        self.assertIn("context window exceeded", s)

    def test_format_is_non_empty(self) -> None:
        self.assertTrue(len(format_engine_error("E", "m")) > 0)


# ─────────────────────────────────────────────────────────────────────────────
# call_claude — exception/failure path surfaces a NON-EMPTY sentinel
# ─────────────────────────────────────────────────────────────────────────────


class TestCallClaudeErrorSurfacing(unittest.TestCase):
    """Mock subprocess.run to fail; assert the surfaced output is a non-empty
    sentinel containing the exception class + message."""

    def setUp(self) -> None:
        # Force the CLI to resolve so we exercise the subprocess path (not the
        # cli-is-None config gap, which is intentionally left as "").
        self._patch_cli = mock.patch.object(
            claude_module, "_resolve_cli", return_value="/fake/claude"
        )
        self._patch_cli.start()

    def tearDown(self) -> None:
        self._patch_cli.stop()

    def test_generic_exception_surfaced(self) -> None:
        """A representative LLM failure (context overflow) raised by the call
        must come back as a non-empty sentinel carrying type + message."""
        msg = "context window exceeded: input 3.41 MB > 200k tokens"
        with mock.patch.object(
            claude_module.subprocess, "run",
            side_effect=RuntimeError(msg),
        ):
            out = call_claude("a very large rendered template")
        # NEW contract: non-empty + carries the cause.
        self.assertTrue(out, "engine must NOT return empty string on exception")
        self.assertTrue(out.startswith("RDG-ENGINE-ERROR:"))
        self.assertIn("RuntimeError", out)
        self.assertIn("context window exceeded", out)

    def test_called_process_error_surfaced(self) -> None:
        """A subprocess.CalledProcessError (representative API/binary failure)
        must surface its class name + detail."""
        import subprocess
        exc = subprocess.CalledProcessError(
            returncode=2, cmd=["claude", "--print"], stderr="api 500"
        )
        with mock.patch.object(
            claude_module.subprocess, "run", side_effect=exc,
        ):
            out = call_claude("prompt")
        self.assertTrue(out)
        self.assertIn("RDG-ENGINE-ERROR", out)
        self.assertIn("CalledProcessError", out)

    def test_timeout_surfaced(self) -> None:
        """A TimeoutExpired must surface as a non-empty sentinel naming the
        timeout (not silently return '')."""
        import subprocess
        with mock.patch.object(
            claude_module.subprocess, "run",
            side_effect=subprocess.TimeoutExpired(cmd="claude", timeout=600),
        ):
            out = call_claude("prompt")
        self.assertTrue(out)
        self.assertIn("RDG-ENGINE-ERROR", out)
        self.assertIn("TimeoutExpired", out)
        self.assertIn("timed out", out.lower())

    def test_nonzero_cli_exit_surfaced(self) -> None:
        """A non-zero CLI exit (cause in stderr) must surface, not return ''."""
        import subprocess
        completed = subprocess.CompletedProcess(
            args=["claude", "--print"], returncode=1,
            stdout="", stderr="Error: input exceeds maximum context length",
        )
        with mock.patch.object(
            claude_module.subprocess, "run", return_value=completed,
        ):
            out = call_claude("prompt")
        self.assertTrue(out)
        self.assertIn("RDG-ENGINE-ERROR", out)
        self.assertIn("input exceeds maximum context length", out)

    # ── Success / genuine-empty paths: MUST be preserved ────────────────────

    def test_success_returns_response_unchanged(self) -> None:
        """STRICT SCOPE: a successful call returns the model text verbatim —
        no sentinel wrapping."""
        import subprocess
        completed = subprocess.CompletedProcess(
            args=["claude", "--print"], returncode=0,
            stdout="## Report\n\nGenuine model output.\n", stderr="",
        )
        with mock.patch.object(
            claude_module.subprocess, "run", return_value=completed,
        ):
            out = call_claude("prompt")
        self.assertEqual(out, "## Report\n\nGenuine model output.\n")
        self.assertNotIn("RDG-ENGINE-ERROR", out)

    def test_genuine_empty_no_exception_stays_empty(self) -> None:
        """CONSTRAINT 1: model returns "" with NO exception and exit 0 — this
        is the legitimate genuine-empty path. It must stay "" (the 0-byte audit
        covers it); it must NOT be converted into an error sentinel."""
        import subprocess
        completed = subprocess.CompletedProcess(
            args=["claude", "--print"], returncode=0,
            stdout="", stderr="",
        )
        with mock.patch.object(
            claude_module.subprocess, "run", return_value=completed,
        ):
            out = call_claude("prompt")
        self.assertEqual(out, "")


# ─────────────────────────────────────────────────────────────────────────────
# Revert guards — these turn RED if the fix is reverted to `return ""`
# ─────────────────────────────────────────────────────────────────────────────


class TestRevertGuards(unittest.TestCase):
    """The OLD (forbidden) contract returned "" on exception. These assert the
    engine does NOT do that anymore — reverting the fix makes them fail."""

    def setUp(self) -> None:
        self._patch_cli = mock.patch.object(
            claude_module, "_resolve_cli", return_value="/fake/claude"
        )
        self._patch_cli.start()

    def tearDown(self) -> None:
        self._patch_cli.stop()

    def test_exception_path_is_not_empty(self) -> None:
        with mock.patch.object(
            claude_module.subprocess, "run",
            side_effect=RuntimeError("boom"),
        ):
            out = call_claude("prompt")
        self.assertNotEqual(
            out, "",
            "REGRESSION: engine swallowed the exception to '' (pre-fix bug). "
            "The exception path must surface a non-empty sentinel.",
        )


def main() -> int:
    loader = unittest.TestLoader()
    suite = loader.loadTestsFromModule(sys.modules[__name__])
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)
    return 0 if result.wasSuccessful() else 1


if __name__ == "__main__":
    sys.exit(main())
