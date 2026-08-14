#!/usr/bin/env python3
r"""
RDG Golden-Test Suite Runner (S10).

Validates the planted-violation fixture suite under
`tests/golden/` against expected verdicts.

Two modes:

  (1) Structural mode (default, free, fast):
      - Every fixture directory has: input/, expected-output.md,
        fixture.json, README.md.
      - expected-output.md conforms to Convention 1 (header +
        machine-readable JSON fence + summary).
      - fixture.json conforms to the fixture schema (required
        keys present, types correct).
      - The JSON fence in expected-output.md is parseable and
        semantically consistent with fixture.json.
      - For llm-switch-fixtures: every case file has required
        keys, label.substantialChange is a bool, before/after
        are non-empty strings.

  (2) Live mode (--live, costs API calls):
      - For each fixture, invokes the corresponding RDG pipeline
        against the fixture's input/ directory.
      - Compares the actual LLM verdict against
        expected-output.md.
      - Reports divergences with verbatim diffs.

Design constraints (per the S10 dispatch prompt):
  - Stdlib only (unittest, pathlib, json, subprocess, argparse,
    difflib). No new top-level deps.
  - No `??`-equivalent silent fallbacks in fixture-runner code.
    Missing required keys MUST raise; defaults are acceptable
    ONLY at the argparse boundary (e.g., --filter default '').
  - Convention 1 escape: `--\->` in JSON strings is unescaped on
    parse.
  - Failures throw with verbatim context, not silent log.

Exit codes:
  0  All fixtures pass.
  1  One or more fixtures failed structural validation.
  2  Live mode: pipeline invocation failed or LLM verdict diverged.

Plan reference:
  docs/plans/2026-05-17_codification-doctrine-substrate-health.md §S10
"""

from __future__ import annotations

import argparse
import difflib
import json
import re
import subprocess
import sys
import unittest
from pathlib import Path
from typing import Any

# ─────────────────────────────────────────────────────────────────────────────
# Constants
# ─────────────────────────────────────────────────────────────────────────────

TESTS_DIR = Path(__file__).resolve().parent
GOLDEN_DIR = TESTS_DIR / "golden"
SWITCH_DIR = GOLDEN_DIR / "llm-switch-fixtures"
SWITCH_CASES_DIR = SWITCH_DIR / "cases"

# Categories that follow the planted-violation fixture format
# (input/, expected-output.md, fixture.json, README.md).
VIOLATION_CATEGORIES = ("math-violations", "doctrine-stale", "llm-bias-anchor")

# Convention 1 fence delimiters (with escape support).
FENCE_OPEN = "<!-- machine-readable"
FENCE_CLOSE = "-->"
ESCAPED_CLOSE = "--\\->"  # generators escape '-->' inside JSON strings

# Required keys per fixture.json (per S10 design).
REQUIRED_FIXTURE_KEYS = {
    "schemaVersion",
    "fixtureId",
    "category",
    "rdgPipeline",
    "promptFile",
    "inputFiles",
    "expectedVerdict",
}

# Required keys inside the expected-output.md machine-readable
# data block.
REQUIRED_DATA_KEYS = {"fixtureId", "rdgPipeline", "expectedVerdict"}

# Required keys per llm-switch case.
REQUIRED_SWITCH_KEYS = {
    "schemaVersion",
    "fixtureId",
    "pipeline",
    "facet",
    "before",
    "after",
    "label",
}


# ─────────────────────────────────────────────────────────────────────────────
# Errors
# ─────────────────────────────────────────────────────────────────────────────


class FixtureError(Exception):
    """Raised when a fixture is malformed. Carries verbatim context."""


class GoldenDivergenceError(Exception):
    """Raised in live mode when LLM verdict diverges from expected."""


# ─────────────────────────────────────────────────────────────────────────────
# Fixture loading + parsing
# ─────────────────────────────────────────────────────────────────────────────


def discover_violation_fixtures(filter_substring: str = "") -> list[Path]:
    """Walk GOLDEN_DIR and return every violation-fixture directory.

    A violation fixture is any path with form
    `golden/<category>/<fixture-name>/` where <category> is in
    VIOLATION_CATEGORIES.
    """
    fixtures: list[Path] = []
    for category in VIOLATION_CATEGORIES:
        category_dir = GOLDEN_DIR / category
        if not category_dir.is_dir():
            continue
        for child in sorted(category_dir.iterdir()):
            if not child.is_dir():
                continue
            fixture_id = f"{category}/{child.name}"
            if filter_substring and filter_substring not in fixture_id:
                continue
            fixtures.append(child)
    return fixtures


def discover_switch_cases(filter_substring: str = "") -> list[Path]:
    """Return every llm-switch case file (cases/*.json)."""
    if not SWITCH_CASES_DIR.is_dir():
        return []
    cases: list[Path] = []
    for path in sorted(SWITCH_CASES_DIR.glob("*.json")):
        if filter_substring and filter_substring not in path.name:
            continue
        cases.append(path)
    return cases


def load_fixture_json(fixture_dir: Path) -> dict[str, Any]:
    """Load and validate fixture.json. Raises FixtureError on any issue."""
    fixture_json_path = fixture_dir / "fixture.json"
    if not fixture_json_path.is_file():
        raise FixtureError(
            f"Missing fixture.json: {fixture_json_path}"
        )
    try:
        with fixture_json_path.open("r") as f:
            data = json.load(f)
    except json.JSONDecodeError as exc:
        raise FixtureError(
            f"Malformed JSON in {fixture_json_path}: {exc}"
        ) from exc

    if not isinstance(data, dict):
        raise FixtureError(
            f"fixture.json top-level must be an object: {fixture_json_path}"
        )

    missing = REQUIRED_FIXTURE_KEYS - set(data.keys())
    if missing:
        raise FixtureError(
            f"fixture.json {fixture_json_path} missing required keys: "
            f"{sorted(missing)}"
        )

    if not isinstance(data["inputFiles"], list) or len(data["inputFiles"]) == 0:
        raise FixtureError(
            f"fixture.json {fixture_json_path} inputFiles must be non-empty list"
        )

    return data


def extract_machine_readable_block(markdown: str, source_path: Path) -> dict[str, Any]:
    """Parse the Convention 1 machine-readable JSON fence from a markdown doc."""
    open_idx = markdown.find(FENCE_OPEN)
    if open_idx == -1:
        raise FixtureError(
            f"{source_path}: missing Convention 1 fence opener `{FENCE_OPEN}`"
        )

    after_open = markdown[open_idx + len(FENCE_OPEN):]
    close_idx = after_open.find(FENCE_CLOSE)
    if close_idx == -1:
        raise FixtureError(
            f"{source_path}: missing Convention 1 fence closer `{FENCE_CLOSE}`"
        )

    raw_json = after_open[:close_idx].strip()
    # Reverse Convention 1 escape: `--\->` → `-->` inside JSON strings.
    unescaped = raw_json.replace(ESCAPED_CLOSE, FENCE_CLOSE)

    try:
        parsed = json.loads(unescaped)
    except json.JSONDecodeError as exc:
        raise FixtureError(
            f"{source_path}: Convention 1 JSON fence is not valid JSON: {exc}\n"
            f"--- raw block ---\n{raw_json}\n--- end ---"
        ) from exc

    if not isinstance(parsed, dict):
        raise FixtureError(
            f"{source_path}: Convention 1 fence must contain a JSON object"
        )

    for required in ("schemaVersion", "generatedAt", "data"):
        if required not in parsed:
            raise FixtureError(
                f"{source_path}: Convention 1 fence missing required key "
                f"`{required}`"
            )

    data = parsed["data"]
    if not isinstance(data, dict):
        raise FixtureError(
            f"{source_path}: Convention 1 fence `data` must be an object"
        )

    missing_data = REQUIRED_DATA_KEYS - set(data.keys())
    if missing_data:
        raise FixtureError(
            f"{source_path}: Convention 1 fence data missing keys: "
            f"{sorted(missing_data)}"
        )

    return parsed


def load_expected_output(fixture_dir: Path) -> dict[str, Any]:
    """Load expected-output.md and parse its Convention 1 fence."""
    expected_path = fixture_dir / "expected-output.md"
    if not expected_path.is_file():
        raise FixtureError(f"Missing expected-output.md: {expected_path}")
    text = expected_path.read_text()
    return extract_machine_readable_block(text, expected_path)


def load_switch_case(case_path: Path) -> dict[str, Any]:
    """Load and validate an llm-switch case file."""
    try:
        with case_path.open("r") as f:
            data = json.load(f)
    except json.JSONDecodeError as exc:
        raise FixtureError(
            f"Malformed JSON in {case_path}: {exc}"
        ) from exc

    if not isinstance(data, dict):
        raise FixtureError(
            f"{case_path}: top-level must be an object"
        )

    missing = REQUIRED_SWITCH_KEYS - set(data.keys())
    if missing:
        raise FixtureError(
            f"{case_path}: missing required keys {sorted(missing)}"
        )

    if not isinstance(data["before"], str) or not data["before"].strip():
        raise FixtureError(
            f"{case_path}: `before` must be non-empty string"
        )
    if not isinstance(data["after"], str) or not data["after"].strip():
        raise FixtureError(
            f"{case_path}: `after` must be non-empty string"
        )

    label = data["label"]
    if not isinstance(label, dict):
        raise FixtureError(
            f"{case_path}: `label` must be an object"
        )
    if "substantialChange" not in label:
        raise FixtureError(
            f"{case_path}: `label.substantialChange` missing"
        )
    if not isinstance(label["substantialChange"], bool):
        raise FixtureError(
            f"{case_path}: `label.substantialChange` must be bool, got "
            f"{type(label['substantialChange']).__name__}"
        )
    if "rationale" not in label or not isinstance(label["rationale"], str):
        raise FixtureError(
            f"{case_path}: `label.rationale` must be string"
        )

    return data


# ─────────────────────────────────────────────────────────────────────────────
# Structural validation (default mode)
# ─────────────────────────────────────────────────────────────────────────────


def validate_violation_fixture(fixture_dir: Path) -> None:
    """Run all structural checks on one violation fixture. Raise on any failure."""
    # 1. fixture.json well-formed
    fixture = load_fixture_json(fixture_dir)

    # 2. README.md present
    readme = fixture_dir / "README.md"
    if not readme.is_file():
        raise FixtureError(f"Missing README.md: {readme}")

    # 3. input/ present with at least the declared files
    input_dir = fixture_dir / "input"
    if not input_dir.is_dir():
        raise FixtureError(f"Missing input/ directory: {input_dir}")

    for declared in fixture["inputFiles"]:
        declared_path = fixture_dir / declared
        if not declared_path.is_file():
            raise FixtureError(
                f"fixture.json declares input {declared} but file missing at "
                f"{declared_path}"
            )

    # 4. expected-output.md parses, Convention 1 conformant
    expected = load_expected_output(fixture_dir)
    expected_data = expected["data"]

    # 5. Cross-consistency: fixture.json and expected-output.md agree on
    #    fixtureId, rdgPipeline, expectedVerdict.
    # Both sources are pre-validated to contain these keys above (load_fixture_json
    # enforces REQUIRED_FIXTURE_KEYS; extract_machine_readable_block enforces
    # REQUIRED_DATA_KEYS). Direct indexing here is intentional fail-loud — a
    # missing key at this point means the upstream validation has a bug.
    for shared_key in ("fixtureId", "rdgPipeline", "expectedVerdict"):
        a = fixture[shared_key]
        b = expected_data[shared_key]
        if a != b:
            raise FixtureError(
                f"{fixture_dir.name}: fixture.json `{shared_key}={a!r}` "
                f"diverges from expected-output.md `{shared_key}={b!r}`"
            )


def validate_switch_case(case_path: Path) -> None:
    """Run structural checks on one llm-switch case."""
    load_switch_case(case_path)


# ─────────────────────────────────────────────────────────────────────────────
# Live mode (invokes real RDG pipeline against fixture inputs)
# ─────────────────────────────────────────────────────────────────────────────


def find_rtb_manual_root() -> Path | None:
    """Locate the rtb-manual repo by walking up from this file.

    rtb-manual is the SIBLING of rdg-notebook in the parent monorepo:
        <monorepo>/apps/rtb-manual/
        <monorepo>/rdg-notebook/
    """
    # tests/ -> reactive-docgen/ -> rdg-notebook/ -> monorepo root
    candidate = TESTS_DIR.parent.parent.parent / "apps" / "rtb-manual"
    if candidate.is_dir() and (candidate / "package.json").is_file():
        return candidate
    return None


def run_live_pipeline(fixture_dir: Path, fixture: dict[str, Any]) -> str:
    """Invoke the RDG pipeline against the fixture's input/ directory.

    Returns the verbatim verdict text.

    Note: live mode is an OPT-IN integration test. It requires:
      - rtb-manual sibling repo
      - rdg-notebook bin/rdg executable
      - claude CLI on PATH (RDG_PRIMARY=claude)
      - RDG cache populated or willingness to pay API call

    The live path constructs a transient .rdg pipeline that points
    at the fixture's input/ directory, invokes the rdg engine, and
    captures the output.
    """
    rtb_root = find_rtb_manual_root()
    if rtb_root is None:
        raise GoldenDivergenceError(
            f"Live mode requires rtb-manual sibling. Searched at "
            f"{TESTS_DIR.parent.parent.parent / 'apps' / 'rtb-manual'}"
        )

    rdg_bin = TESTS_DIR.parent / "bin" / "rdg"
    if not rdg_bin.is_file():
        raise GoldenDivergenceError(
            f"Live mode requires rdg engine at {rdg_bin}"
        )

    pipeline = fixture["rdgPipeline"]
    prompt_file = fixture["promptFile"]
    # We need to construct a transient .rdg that points at the fixture input.
    # This is a thin invocation; full pipeline construction is out of scope.
    # For S10, we report a NotImplemented divergence so the user knows live
    # mode is scaffolded but requires fixture-pipeline binding work.
    raise GoldenDivergenceError(
        f"Live mode for fixture {fixture['fixtureId']} not yet wired. "
        f"Pipeline `{pipeline}` would invoke prompt `{prompt_file}` against "
        f"{fixture_dir / 'input'}. Live invocation is scaffolded but the "
        f"transient .rdg construction is deferred to S10-follow-up — wire "
        f"this by writing a .rdg.template alongside each fixture and "
        f"substituting the input path before invoking `rdg run`."
    )


def diff_strings(expected: str, actual: str, label_a: str, label_b: str) -> str:
    """Produce a unified diff between two strings for error messages."""
    expected_lines = expected.splitlines(keepends=True)
    actual_lines = actual.splitlines(keepends=True)
    diff = difflib.unified_diff(
        expected_lines, actual_lines,
        fromfile=label_a, tofile=label_b,
        lineterm="",
    )
    return "".join(diff)


# ─────────────────────────────────────────────────────────────────────────────
# Test cases (unittest)
# ─────────────────────────────────────────────────────────────────────────────


# Module-level filter — settable from main() so test discovery sees it.
_FILTER: str = ""
_LIVE: bool = False


class TestViolationFixturesStructural(unittest.TestCase):
    """Structural validation for planted-violation fixtures."""

    def test_violation_fixtures_present(self) -> None:
        """At least one fixture must exist per category (sanity check)."""
        for category in VIOLATION_CATEGORIES:
            category_dir = GOLDEN_DIR / category
            self.assertTrue(
                category_dir.is_dir(),
                f"Missing category directory: {category_dir}",
            )
            child_dirs = [c for c in category_dir.iterdir() if c.is_dir()]
            self.assertGreaterEqual(
                len(child_dirs), 1,
                f"Category {category} has no fixture subdirectories",
            )

    def test_each_fixture_validates(self) -> None:
        """Walk every fixture and run structural validation."""
        fixtures = discover_violation_fixtures(_FILTER)
        self.assertGreater(
            len(fixtures), 0,
            f"No fixtures discovered (filter={_FILTER!r})",
        )
        failures: list[str] = []
        for fixture_dir in fixtures:
            try:
                validate_violation_fixture(fixture_dir)
            except FixtureError as exc:
                failures.append(f"FIXTURE FAIL [{fixture_dir.name}]: {exc}")
        if failures:
            self.fail("\n\n".join(failures))


class TestSwitchFixturesStructural(unittest.TestCase):
    """Structural validation for llm-switch fixture cases."""

    def test_switch_cases_present(self) -> None:
        """The cases/ directory must contain at least one .json file."""
        self.assertTrue(
            SWITCH_CASES_DIR.is_dir(),
            f"Missing switch cases dir: {SWITCH_CASES_DIR}",
        )
        cases = list(SWITCH_CASES_DIR.glob("*.json"))
        self.assertGreater(
            len(cases), 0,
            f"No llm-switch cases found in {SWITCH_CASES_DIR}",
        )

    def test_each_switch_case_validates(self) -> None:
        """Every case file conforms to the switch-fixture schema."""
        cases = discover_switch_cases(_FILTER)
        if not cases:
            self.skipTest(f"No switch cases match filter={_FILTER!r}")
        failures: list[str] = []
        for case_path in cases:
            try:
                validate_switch_case(case_path)
            except FixtureError as exc:
                failures.append(f"SWITCH FAIL [{case_path.name}]: {exc}")
        if failures:
            self.fail("\n\n".join(failures))

    def test_switch_cases_have_label_balance(self) -> None:
        """Sanity: at least one substantialChange=true AND one =false.

        Without both classes the predicate has no negative space to
        distinguish — divergence_rate would be trivially zero.
        """
        cases = discover_switch_cases("")
        if not cases:
            self.skipTest("No switch cases to balance-check")
        labels = [load_switch_case(c)["label"]["substantialChange"] for c in cases]
        self.assertIn(True, labels, "No substantialChange=true cases")
        self.assertIn(False, labels, "No substantialChange=false cases")


class TestLiveMode(unittest.TestCase):
    """Live mode: invoke real RDG pipelines against fixture inputs.

    Skipped unless --live is set. Costs API calls when run.
    """

    def test_live_violation_fixtures(self) -> None:
        if not _LIVE:
            self.skipTest("Live mode disabled (use --live to enable)")
        fixtures = discover_violation_fixtures(_FILTER)
        failures: list[str] = []
        for fixture_dir in fixtures:
            fixture = load_fixture_json(fixture_dir)
            try:
                actual = run_live_pipeline(fixture_dir, fixture)
            except GoldenDivergenceError as exc:
                failures.append(f"LIVE FAIL [{fixture_dir.name}]: {exc}")
                continue
            expected = (fixture_dir / "expected-output.md").read_text()
            if expected.strip() not in actual.strip():
                diff = diff_strings(
                    expected, actual,
                    "expected-output.md", "rdg actual",
                )
                failures.append(
                    f"LIVE DIVERGE [{fixture_dir.name}]:\n{diff}"
                )
        if failures:
            self.fail("\n\n".join(failures))


# ─────────────────────────────────────────────────────────────────────────────
# Entrypoint
# ─────────────────────────────────────────────────────────────────────────────


def main() -> int:
    global _FILTER, _LIVE
    parser = argparse.ArgumentParser(
        description="RDG golden-test suite runner (S10)",
    )
    parser.add_argument(
        "--filter",
        default="",
        help="Substring filter on fixture id / case filename",
    )
    parser.add_argument(
        "--live",
        action="store_true",
        help="Enable live RDG pipeline invocation (costs API calls)",
    )
    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="Verbose test output",
    )
    args = parser.parse_args()

    _FILTER = args.filter
    _LIVE = args.live

    # Build a suite explicitly so we control the order.
    loader = unittest.TestLoader()
    suite = unittest.TestSuite()
    suite.addTests(loader.loadTestsFromTestCase(TestViolationFixturesStructural))
    suite.addTests(loader.loadTestsFromTestCase(TestSwitchFixturesStructural))
    suite.addTests(loader.loadTestsFromTestCase(TestLiveMode))

    verbosity = 2 if args.verbose else 1
    runner = unittest.TextTestRunner(verbosity=verbosity)
    result = runner.run(suite)

    if not result.wasSuccessful():
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
