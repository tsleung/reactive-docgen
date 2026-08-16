#!/usr/bin/env python3
"""
RDG LLM-Switch Regression Test Suite (S11).

Spec: a consumer repo §S11
Anchor: rdg-notebook/reactive-docgen/tests/golden/llm-switch-fixtures/cases/*.json (S10)

Two modes:

  (1) Structural mode (default, no API calls, fast):
      - Fixture-file schema validation (label.substantialChange is bool, etc.)
      - Switch module imports cleanly.
      - Byte-equality short-circuit works for byte-identical inputs.
      - Claude response parser handles strict + lenient + malformed responses.
      - Shadow wrapper rejects `skip_pipeline=True` (ShadowModeBypassError).
      - Shadow wrapper writes the schema-version header + invocation rows.

  (2) Live mode (--live, costs Claude calls):
      - For every fixture in cases/, invoke has_substantially_changed()
        with prev=before, current=after, and assert decision matches
        label.substantialChange.
      - Track per-case latency; fail if any individual call exceeds
        SWITCH_LATENCY_BUDGET_MS (5 seconds).

Exit codes:
  0  All tests pass.
  1  One or more tests failed.

Per dispatch prompt §Verification step 2: this script exits 0 in structural
(default) mode.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from typing import Any
from unittest import mock

# Make the rdg package importable without installing the project.
TESTS_DIR = Path(__file__).resolve().parent
REACTIVE_DOCGEN_DIR = TESTS_DIR.parent
SRC_DIR = REACTIVE_DOCGEN_DIR / "src"
SWITCH_CASES_DIR = TESTS_DIR / "golden" / "llm-switch-fixtures" / "cases"

if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

# These imports are intentionally INSIDE the sys.path setup above. The
# linter will complain; it's fine.
from rdg import switch as switch_module  # noqa: E402
from rdg.switch import (  # noqa: E402
    DEFAULT_SWITCH_MODEL,
    LOAD_BEARING_FLAG,
    SWITCH_LATENCY_BUDGET_MS,
    SubstantialChangeResult,
    SwitchUnavailableError,
    has_substantially_changed,
)
from rdg import switch_shadow as shadow_module  # noqa: E402
from rdg.switch_shadow import (  # noqa: E402
    SHADOW_SCHEMA_VERSION,
    ShadowInvocationRecord,
    ShadowModeBypassError,
    run_shadow,
)


# ─────────────────────────────────────────────────────────────────────────────
# CLI argument (sets module-level LIVE flag before test discovery runs)
# ─────────────────────────────────────────────────────────────────────────────


_LIVE = False


def _parse_args() -> tuple[bool, list[str]]:
    parser = argparse.ArgumentParser(description="S11 switch regression tests")
    parser.add_argument(
        "--live",
        action="store_true",
        help=(
            "Run live mode (invokes the real Claude CLI for each fixture). "
            "Default is structural-only — mocked Claude calls."
        ),
    )
    parser.add_argument(
        "remaining",
        nargs=argparse.REMAINDER,
        help="Forwarded to unittest.",
    )
    args = parser.parse_args()
    return args.live, args.remaining or []


# ─────────────────────────────────────────────────────────────────────────────
# Fixture loading
# ─────────────────────────────────────────────────────────────────────────────


def _load_switch_cases() -> list[dict[str, Any]]:
    """Load every S10 llm-switch case file. Returns empty list if dir missing."""
    if not SWITCH_CASES_DIR.is_dir():
        return []
    cases: list[dict[str, Any]] = []
    for path in sorted(SWITCH_CASES_DIR.glob("*.json")):
        with path.open("r", encoding="utf-8") as f:
            cases.append(json.load(f))
    return cases


# ─────────────────────────────────────────────────────────────────────────────
# Structural tests (always run — no Claude calls)
# ─────────────────────────────────────────────────────────────────────────────


class TestSwitchModuleStructure(unittest.TestCase):
    """Smoke-tests the switch module's static contracts."""

    def test_module_imports_cleanly(self) -> None:
        self.assertTrue(hasattr(switch_module, "has_substantially_changed"))
        self.assertTrue(hasattr(switch_module, "SubstantialChangeResult"))
        self.assertTrue(hasattr(switch_module, "SwitchUnavailableError"))
        self.assertTrue(hasattr(switch_module, "LOAD_BEARING_FLAG"))

    def test_load_bearing_flag_is_false(self) -> None:
        """STRUCTURAL INVARIANT: the switch must ship as non-load-bearing."""
        self.assertEqual(LOAD_BEARING_FLAG, False)
        self.assertEqual(
            switch_module.LOAD_BEARING_FLAG,
            False,
            (
                "LOAD_BEARING_FLAG MUST be False at HEAD. Flipping this to "
                "True requires a founder commit per plan §S11 + "
                "Convention 6 (>=14 days shadow + divergence_rate < 0.05)."
            ),
        )

    def test_default_model_is_sonnet_4_6(self) -> None:
        self.assertEqual(DEFAULT_SWITCH_MODEL, "claude-sonnet-4-6")

    def test_latency_budget_is_5_seconds(self) -> None:
        self.assertEqual(SWITCH_LATENCY_BUDGET_MS, 5_000)


class TestSubstantialChangeResult(unittest.TestCase):
    def test_valid_construction(self) -> None:
        r = SubstantialChangeResult(
            decision=1,
            confidence="high",
            rationale="ok",
            latency_ms=42,
            source="claude",
        )
        self.assertEqual(r.decision, 1)

    def test_invalid_decision_raises(self) -> None:
        with self.assertRaises(ValueError):
            SubstantialChangeResult(
                decision=2,
                confidence="high",
                rationale="ok",
                latency_ms=1,
                source="claude",
            )

    def test_invalid_confidence_raises(self) -> None:
        with self.assertRaises(ValueError):
            SubstantialChangeResult(
                decision=0,
                confidence="absolute",  # not in allowed set
                rationale="ok",
                latency_ms=1,
                source="claude",
            )

    def test_invalid_source_raises(self) -> None:
        with self.assertRaises(ValueError):
            SubstantialChangeResult(
                decision=0,
                confidence="high",
                rationale="ok",
                latency_ms=1,
                source="gemini",
            )


class TestByteEqualityShortCircuit(unittest.TestCase):
    """Verify the free fast path."""

    def test_byte_identical_inputs_short_circuit(self) -> None:
        text = "export const x = 1;"
        prev_hash = switch_module._hash_current_input(text)
        result = has_substantially_changed(
            prev_input_hash=prev_hash,
            prev_verdict="PASS",
            current_input=text,
        )
        self.assertEqual(result.decision, 0)
        self.assertEqual(result.source, "byte-cache-equality")
        self.assertEqual(result.latency_ms, 0)
        self.assertEqual(result.confidence, "high")

    def test_empty_prev_hash_does_not_short_circuit(self) -> None:
        """Empty prev hash → byte-equality cannot conclude; must consult switch."""
        short_circuit = switch_module._byte_equality_short_circuit(
            "", "any input"
        )
        self.assertIsNone(short_circuit)


class TestClaudeResponseParser(unittest.TestCase):
    """Parser fuzzing — verify fail-loud on malformed responses."""

    def test_strict_format_parses(self) -> None:
        raw = "DECISION: 1\nRATIONALE: introduces a ?? fallback in the policy path\n"
        decision, rationale, confidence = switch_module._parse_claude_response(raw)
        self.assertEqual(decision, 1)
        self.assertIn("??", rationale)
        self.assertEqual(confidence, "high")

    def test_strict_zero_parses(self) -> None:
        raw = "DECISION: 0\nRATIONALE: whitespace only\n"
        decision, _, confidence = switch_module._parse_claude_response(raw)
        self.assertEqual(decision, 0)
        self.assertEqual(confidence, "high")

    def test_lenient_with_preamble(self) -> None:
        raw = (
            "After analyzing the diff, my answer is below.\n"
            "DECISION: 1\n"
            "RATIONALE: net-new function\n"
        )
        decision, _, _ = switch_module._parse_claude_response(raw)
        self.assertEqual(decision, 1)

    def test_missing_rationale_downgrades_confidence(self) -> None:
        raw = "DECISION: 1\n"
        _, rationale, confidence = switch_module._parse_claude_response(raw)
        self.assertEqual(confidence, "low")
        self.assertIn("no rationale", rationale.lower())

    def test_empty_response_raises(self) -> None:
        with self.assertRaises(ValueError):
            switch_module._parse_claude_response("")

    def test_no_decision_line_raises(self) -> None:
        with self.assertRaises(ValueError):
            switch_module._parse_claude_response(
                "I cannot answer this question without more context.\n"
            )


class TestSwitchTypeValidation(unittest.TestCase):
    """Programmer-error inputs MUST raise immediately."""

    def test_non_string_current_input_raises(self) -> None:
        with self.assertRaises(ValueError):
            has_substantially_changed(
                prev_input_hash="abc",
                prev_verdict="PASS",
                current_input=12345,  # type: ignore[arg-type]
            )

    def test_non_string_prev_hash_raises(self) -> None:
        with self.assertRaises(ValueError):
            has_substantially_changed(
                prev_input_hash=None,  # type: ignore[arg-type]
                prev_verdict="PASS",
                current_input="x",
            )

    def test_non_string_prev_verdict_raises(self) -> None:
        with self.assertRaises(ValueError):
            has_substantially_changed(
                prev_input_hash="abc",
                prev_verdict=42,  # type: ignore[arg-type]
                current_input="x",
            )


class TestSwitchUnavailableRaises(unittest.TestCase):
    """When Claude CLI is not resolvable, the switch must raise — not silently default."""

    def setUp(self) -> None:
        # Clear the module-level resolver cache so each test starts fresh.
        switch_module._resolved_cli_path = None

    def test_unavailable_claude_raises(self) -> None:
        with mock.patch.object(
            switch_module, "_resolve_cli", return_value=None
        ):
            with self.assertRaises(SwitchUnavailableError) as ctx:
                has_substantially_changed(
                    prev_input_hash="diffhash",  # different from current to bypass byte-equality
                    prev_verdict="PASS",
                    current_input="new content",
                )
            self.assertIn("Claude CLI not available", str(ctx.exception))


class TestSwitchMockedClaude(unittest.TestCase):
    """End-to-end with a mocked subprocess.run — no real Claude call."""

    def setUp(self) -> None:
        switch_module._resolved_cli_path = None

    def _make_completed_process(
        self, stdout: str, returncode: int = 0, stderr: str = ""
    ) -> Any:
        import subprocess
        return subprocess.CompletedProcess(
            args=["claude", "--print"], returncode=returncode,
            stdout=stdout, stderr=stderr,
        )

    def test_substantive_decision_round_trip(self) -> None:
        with mock.patch.object(
            switch_module, "_resolve_cli", return_value="/fake/claude"
        ), mock.patch.object(
            switch_module.subprocess, "run",
            return_value=self._make_completed_process(
                "DECISION: 1\nRATIONALE: introduces ?? fallback\n"
            ),
        ):
            result = has_substantially_changed(
                prev_input_hash="prevhash",
                prev_verdict="PASS",
                current_input="something different",
            )
            self.assertEqual(result.decision, 1)
            self.assertEqual(result.source, "claude")
            self.assertEqual(result.confidence, "high")

    def test_cosmetic_decision_round_trip(self) -> None:
        with mock.patch.object(
            switch_module, "_resolve_cli", return_value="/fake/claude"
        ), mock.patch.object(
            switch_module.subprocess, "run",
            return_value=self._make_completed_process(
                "DECISION: 0\nRATIONALE: whitespace only\n"
            ),
        ):
            result = has_substantially_changed(
                prev_input_hash="prevhash",
                prev_verdict="PASS",
                current_input="something different",
            )
            self.assertEqual(result.decision, 0)

    def test_claude_nonzero_exit_raises(self) -> None:
        with mock.patch.object(
            switch_module, "_resolve_cli", return_value="/fake/claude"
        ), mock.patch.object(
            switch_module.subprocess, "run",
            return_value=self._make_completed_process(
                "", returncode=1, stderr="auth failed"
            ),
        ):
            with self.assertRaises(SwitchUnavailableError) as ctx:
                has_substantially_changed(
                    prev_input_hash="x", prev_verdict="PASS", current_input="y",
                )
            self.assertIn("auth failed", str(ctx.exception))

    def test_claude_malformed_response_raises(self) -> None:
        with mock.patch.object(
            switch_module, "_resolve_cli", return_value="/fake/claude"
        ), mock.patch.object(
            switch_module.subprocess, "run",
            return_value=self._make_completed_process(
                "I cannot decide.\n"
            ),
        ):
            with self.assertRaises(SwitchUnavailableError):
                has_substantially_changed(
                    prev_input_hash="x", prev_verdict="PASS", current_input="y",
                )


# ─────────────────────────────────────────────────────────────────────────────
# Shadow-mode structural tests
# ─────────────────────────────────────────────────────────────────────────────


class TestShadowModeStructure(unittest.TestCase):
    def test_schema_version_is_experimental(self) -> None:
        """Per plan §S11: schema is marked experimental during shadow window."""
        self.assertEqual(SHADOW_SCHEMA_VERSION, "1.0-experimental")

    def test_skip_pipeline_true_raises_bypass_error(self) -> None:
        """STRUCTURAL ENFORCEMENT: callers cannot skip the pipeline in shadow mode."""
        with self.assertRaises(ShadowModeBypassError) as ctx:
            run_shadow(
                prev_input_hash="x",
                prev_verdict="PASS",
                current_input="y",
                run_pipeline_fn=lambda: None,
                actual_decision_extractor=lambda _v, _r: 0,
                skip_pipeline=True,
            )
        self.assertIn("Refusing to skip", str(ctx.exception))

    def test_pipeline_invoked_unconditionally(self) -> None:
        """The full pipeline MUST run every time, regardless of switch outcome."""
        calls = []

        def fake_pipeline():
            calls.append("pipeline ran")
            return {"verdict": "PASS"}

        with tempfile.TemporaryDirectory() as tmp:
            ledger = Path(tmp) / "shadow.jsonl"
            os.environ["SHADOW_LEDGER_PATH"] = str(ledger)
            try:
                # Force byte-equality path (cheap; deterministic).
                text = "identical"
                prev_hash = switch_module._hash_current_input(text)
                run_shadow(
                    prev_input_hash=prev_hash,
                    prev_verdict="PASS",
                    current_input=text,
                    run_pipeline_fn=fake_pipeline,
                    actual_decision_extractor=lambda _v, _r: 0,
                )
            finally:
                del os.environ["SHADOW_LEDGER_PATH"]

        self.assertEqual(calls, ["pipeline ran"])

    def test_ledger_header_written_on_first_use(self) -> None:
        """Convention 2: schema-version header is the first JSONL line."""
        with tempfile.TemporaryDirectory() as tmp:
            ledger = Path(tmp) / "shadow.jsonl"
            os.environ["SHADOW_LEDGER_PATH"] = str(ledger)
            try:
                text = "any"
                prev_hash = switch_module._hash_current_input(text)
                run_shadow(
                    prev_input_hash=prev_hash,
                    prev_verdict="PASS",
                    current_input=text,
                    run_pipeline_fn=lambda: None,
                    actual_decision_extractor=lambda _v, _r: 0,
                )
                lines = ledger.read_text(encoding="utf-8").strip().split("\n")
                self.assertGreaterEqual(len(lines), 2)
                header = json.loads(lines[0])
                self.assertEqual(
                    header["_meta"]["schemaVersion"], "1.0-experimental"
                )
                self.assertEqual(
                    header["_meta"]["ledger"], "LLM_SWITCH_SHADOW_DIVERGENCE"
                )
                row = json.loads(lines[1])
                self.assertEqual(row["schemaVersion"], "1.0-experimental")
                self.assertIn("switchDecision", row)
                self.assertIn("actualDecision", row)
                self.assertIn("agreed", row)
            finally:
                del os.environ["SHADOW_LEDGER_PATH"]

    def test_invalid_extractor_return_raises(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            ledger = Path(tmp) / "shadow.jsonl"
            os.environ["SHADOW_LEDGER_PATH"] = str(ledger)
            try:
                text = "any"
                prev_hash = switch_module._hash_current_input(text)
                with self.assertRaises(ValueError):
                    run_shadow(
                        prev_input_hash=prev_hash,
                        prev_verdict="PASS",
                        current_input=text,
                        run_pipeline_fn=lambda: None,
                        actual_decision_extractor=lambda _v, _r: 2,
                    )
            finally:
                del os.environ["SHADOW_LEDGER_PATH"]


# ─────────────────────────────────────────────────────────────────────────────
# Fixture-driven tests (mocked by default; live with --live)
# ─────────────────────────────────────────────────────────────────────────────


class TestFixtureRegression(unittest.TestCase):
    """For each S10 fixture, verify the switch produces the labeled decision.

    Structural mode: each case is validated for schema + the switch is asked
    once with mocked Claude producing the LABELED decision (verifies the
    end-to-end plumbing, not the model's accuracy).

    Live mode: real Claude calls; decisions are compared against labels;
    per-case latency is asserted.
    """

    @classmethod
    def setUpClass(cls) -> None:
        cls.cases = _load_switch_cases()

    def setUp(self) -> None:
        switch_module._resolved_cli_path = None

    def test_fixture_set_has_at_least_one_of_each_label(self) -> None:
        """Sanity: the fixture set must include both substantive and cosmetic cases."""
        if not self.cases:
            self.skipTest("no llm-switch fixtures found")
        labels = {c["label"]["substantialChange"] for c in self.cases}
        self.assertIn(True, labels)
        self.assertIn(False, labels)

    def test_fixture_count_matches_s10(self) -> None:
        """S10 shipped 10 fixtures. Plan calls for ~50 by S11 promotion."""
        # We assert >= 10 (not == 10) so adding fixtures doesn't break the test.
        self.assertGreaterEqual(
            len(self.cases),
            10,
            f"Expected >=10 switch fixtures from S10, got {len(self.cases)}",
        )

    def test_all_cases_have_required_keys(self) -> None:
        required = {"schemaVersion", "fixtureId", "pipeline", "facet",
                    "before", "after", "label"}
        for case in self.cases:
            missing = required - set(case.keys())
            self.assertFalse(
                missing,
                f"{case.get('fixtureId', '?')}: missing {sorted(missing)}",
            )

    def test_structural_mode_mocked_round_trip(self) -> None:
        """End-to-end plumbing test: feed each fixture's labeled decision back
        through a mocked Claude and verify the parser + return-value pipeline
        produces the same decision.

        This is the structural-mode regression anchor — the dispatch prompt
        verification step 2 ("npm run rdg:test-switch — exits 0 in structural
        mode (mocked Claude calls)") is satisfied by this test.
        """
        if not self.cases:
            self.skipTest("no llm-switch fixtures found")
        import subprocess

        for case in self.cases:
            fid = case["fixtureId"]
            labeled = 1 if case["label"]["substantialChange"] else 0
            mocked_stdout = (
                f"DECISION: {labeled}\nRATIONALE: mocked for {fid}\n"
            )

            with mock.patch.object(
                switch_module,
                "_resolve_cli",
                return_value="/fake/claude",
            ), mock.patch.object(
                switch_module.subprocess,
                "run",
                return_value=subprocess.CompletedProcess(
                    args=["claude", "--print"], returncode=0,
                    stdout=mocked_stdout, stderr="",
                ),
            ):
                result = has_substantially_changed(
                    prev_input_hash="prevhash",
                    prev_verdict="PASS",
                    current_input=case["after"],
                )
            self.assertEqual(
                result.decision, labeled,
                f"{fid}: mocked round-trip mismatch (expected {labeled}, "
                f"got {result.decision})",
            )

    def test_live_mode_against_fixtures(self) -> None:
        """REAL Claude calls. Each fixture's `after` is sent through the switch
        with the `before`'s MD5 as prev_input_hash; the decision is asserted
        against `label.substantialChange`.

        Also enforces the per-call latency budget (5 seconds).
        """
        if not _LIVE:
            self.skipTest("--live not set; run with --live to enable")
        if not self.cases:
            self.skipTest("no llm-switch fixtures found")

        failures: list[str] = []
        latency_exceedances: list[str] = []

        for case in self.cases:
            fid = case["fixtureId"]
            expected = 1 if case["label"]["substantialChange"] else 0
            prev_hash = switch_module._hash_current_input(case["before"])

            try:
                result = has_substantially_changed(
                    prev_input_hash=prev_hash,
                    prev_verdict="PASS",
                    current_input=case["after"],
                )
            except SwitchUnavailableError as exc:
                failures.append(f"{fid}: SwitchUnavailable: {exc}")
                continue

            if result.decision != expected:
                failures.append(
                    f"{fid}: expected {expected}, got {result.decision} "
                    f"(confidence={result.confidence}, "
                    f"rationale={result.rationale!r})"
                )

            if result.latency_ms > SWITCH_LATENCY_BUDGET_MS:
                latency_exceedances.append(
                    f"{fid}: {result.latency_ms}ms > "
                    f"{SWITCH_LATENCY_BUDGET_MS}ms budget"
                )

        if failures:
            self.fail(
                f"Live-mode divergence on {len(failures)} fixture(s):\n"
                + "\n".join(failures)
            )
        if latency_exceedances:
            self.fail(
                f"Latency-budget exceedance on {len(latency_exceedances)} "
                f"fixture(s):\n" + "\n".join(latency_exceedances)
            )


# ─────────────────────────────────────────────────────────────────────────────
# Entrypoint
# ─────────────────────────────────────────────────────────────────────────────


def main() -> int:
    global _LIVE
    live, remaining = _parse_args()
    _LIVE = live

    # Hand the remainder to unittest. We let it discover within this module.
    argv = [sys.argv[0]] + remaining
    loader = unittest.TestLoader()
    suite = loader.loadTestsFromModule(sys.modules[__name__])
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)

    if result.wasSuccessful():
        return 0
    return 1


if __name__ == "__main__":
    sys.exit(main())
