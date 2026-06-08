"""
RDG LLM-Switch Shadow-Mode Wrapper (S11).

Spec: apps/rtb-manual/docs/plans/2026-05-17_codification-doctrine-substrate-health.md §S11
Plan reference: apps/rtb-manual/docs/notes/2026-05-18_S10_RDG_GOLDEN_TEST_SUITE.md

Purpose
-------
The switch (switch.py) is HIGH RISK — silent semantic miscategorization could
leave audits stale without anyone noticing. Per plan §S11 + Convention 6, the
switch MUST run in shadow mode for >=14 days with `divergence_rate < 0.05` over
>=20 invocations before it can be flipped load-bearing.

Shadow mode means:
  1. The CHEAP switch runs first and emits a 0/1 prediction.
  2. The FULL pipeline runs UNCONDITIONALLY regardless of the switch
     prediction.
  3. The predicate's decision is COMPARED against the full pipeline's
     decision (did the verdict actually change?).
  4. Agreement / disagreement is logged to the divergence ledger.

The wrapper enforces STRUCTURAL INVARIANT: the switch decision is NEVER used
to skip the full pipeline during shadow mode. This is enforced by the
function signature — `run_shadow()` requires both the switch call AND a
`run_pipeline_fn` callable, and always invokes both, in that order.

Promotion
---------
Switching from shadow to load-bearing requires:
  1. `switch.LOAD_BEARING_FLAG = True` (founder commit to switch.py)
  2. AND the divergence-audit (audit-llm-switch-shadow-divergence.ts) reports
     promotion-gate met.

This module DOES NOT consult `LOAD_BEARING_FLAG`. It is shadow-only by
construction. A separate "load-bearing wrapper" would be required to use the
switch for skip-decisions. None exists in this codebase by design — see plan
§Risk concentration.

Ledger schema
-------------
Each shadow invocation appends one line to
`apps/rtb-manual/docs/operations/LLM_SWITCH_SHADOW_DIVERGENCE.generated.jsonl`:

```jsonl
{"_meta":{"schemaVersion":"1.0-experimental","ledger":"LLM_SWITCH_SHADOW_DIVERGENCE","createdAt":"2026-05-18T00:00:00Z","writer":"rdg-notebook/reactive-docgen/src/rdg/switch_shadow.py"}}
{"schemaVersion":"1.0-experimental","timestamp":"...","fixtureId":"...","prevHash":"...","currentHash":"...","switchDecision":0,"switchRationale":"...","actualDecision":1,"actualLatencyMs":12450,"agreed":false}
```

The first line is the schema header per Convention 2. Schema is marked
`experimental` until 14 days of shadow data accumulate per plan §Convention 6 + §S11.
"""

from __future__ import annotations

import json
import logging
import os
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Optional

from .switch import (
    SubstantialChangeResult,
    SwitchUnavailableError,
    has_substantially_changed,
    _hash_current_input,
)


# ─────────────────────────────────────────────────────────────────────────────
# Constants
# ─────────────────────────────────────────────────────────────────────────────

SHADOW_SCHEMA_VERSION = "1.0-experimental"

# Default ledger location. Derived RELATIVE to the rdg-notebook repo so the
# Python module can run independent of where apps/rtb-manual lives — the
# default assumes the canonical sibling-repo layout described in the plan.
#
# This is the ONLY filesystem write the shadow wrapper performs. The path is
# overridable via env var SHADOW_LEDGER_PATH for tests and CI sandboxes.
def _default_ledger_path() -> Path:
    # rdg-notebook/reactive-docgen/src/rdg/switch_shadow.py
    # → walk up to rdg-notebook/ then sideways to ../apps/rtb-manual/...
    here = Path(__file__).resolve()
    # parents: src/rdg → src → reactive-docgen → rdg-notebook
    rdg_notebook = here.parents[3]
    apps_rtb_manual = rdg_notebook.parent / "apps" / "rtb-manual"
    return (
        apps_rtb_manual
        / "docs"
        / "operations"
        / "LLM_SWITCH_SHADOW_DIVERGENCE.generated.jsonl"
    )


def _resolve_ledger_path() -> Path:
    override = os.environ.get("SHADOW_LEDGER_PATH")
    if override:
        return Path(override)
    return _default_ledger_path()


# ─────────────────────────────────────────────────────────────────────────────
# Errors
# ─────────────────────────────────────────────────────────────────────────────


class ShadowModeBypassError(RuntimeError):
    """Raised if a caller attempts to skip the full pipeline based on switch decision.

    Structural enforcement of plan §S11: 'The switch result is NEVER used to
    skip the full pipeline during shadow mode — it is only logged.'
    """


# ─────────────────────────────────────────────────────────────────────────────
# Result type
# ─────────────────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class ShadowInvocationRecord:
    """One shadow-mode invocation's record."""

    schema_version: str
    timestamp: str
    fixture_id: Optional[str]
    prev_hash: str
    current_hash: str
    switch_decision: Optional[int]
    switch_confidence: Optional[str]
    switch_rationale: str
    switch_source: Optional[str]
    switch_latency_ms: Optional[int]
    actual_decision: int  # 0 or 1 from the FULL pipeline
    actual_latency_ms: int
    agreed: bool
    pipeline_result: Any  # opaque; whatever run_pipeline_fn returned

    def to_ledger_dict(self) -> dict[str, Any]:
        """Render to the JSONL row shape (pipeline_result omitted to keep the ledger small)."""
        return {
            "schemaVersion": self.schema_version,
            "timestamp": self.timestamp,
            "fixtureId": self.fixture_id,
            "prevHash": self.prev_hash,
            "currentHash": self.current_hash,
            "switchDecision": self.switch_decision,
            "switchConfidence": self.switch_confidence,
            "switchRationale": self.switch_rationale,
            "switchSource": self.switch_source,
            "switchLatencyMs": self.switch_latency_ms,
            "actualDecision": self.actual_decision,
            "actualLatencyMs": self.actual_latency_ms,
            "agreed": self.agreed,
        }


# ─────────────────────────────────────────────────────────────────────────────
# Ledger writing
# ─────────────────────────────────────────────────────────────────────────────


def _isoformat_utc(epoch: float) -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(epoch))


def _ensure_ledger_header(ledger_path: Path) -> None:
    """Write the Convention 2 schema header iff the ledger does not yet exist."""
    if ledger_path.exists():
        return
    ledger_path.parent.mkdir(parents=True, exist_ok=True)
    header = {
        "_meta": {
            "schemaVersion": SHADOW_SCHEMA_VERSION,
            "ledger": "LLM_SWITCH_SHADOW_DIVERGENCE",
            "createdAt": _isoformat_utc(time.time()),
            "writer": "rdg-notebook/reactive-docgen/src/rdg/switch_shadow.py",
        }
    }
    # O_APPEND-equivalent: open and append. Header is exactly one line so
    # there's no race that could corrupt the structure even under concurrent
    # writers.
    with ledger_path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(header, separators=(",", ":")) + "\n")


def _append_ledger_row(
    ledger_path: Path, row: dict[str, Any]
) -> None:
    """Append a single line to the ledger. Atomic on POSIX up to PIPE_BUF."""
    with ledger_path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(row, separators=(",", ":")) + "\n")


# ─────────────────────────────────────────────────────────────────────────────
# Public API
# ─────────────────────────────────────────────────────────────────────────────


def run_shadow(
    *,
    prev_input_hash: str,
    prev_verdict: str,
    current_input: str,
    run_pipeline_fn: Callable[[], Any],
    actual_decision_extractor: Callable[[Any, Any], int],
    fixture_id: Optional[str] = None,
    ledger_path: Optional[Path] = None,
    skip_pipeline: bool = False,
) -> ShadowInvocationRecord:
    """Run the switch + full pipeline in shadow mode and log divergence.

    BOTH the switch AND `run_pipeline_fn` are invoked. The switch's decision
    is logged but NEVER used to skip `run_pipeline_fn` — structural
    enforcement of plan §S11.

    Args:
        prev_input_hash: MD5 of the prior rendered input (or "" for first
            run).
        prev_verdict: Prior pipeline verdict string (for switch context;
            informational only).
        current_input: The current rendered input.
        run_pipeline_fn: Callable that runs the FULL upstream pipeline and
            returns whatever output the caller wants to compare. This is
            invoked UNCONDITIONALLY.
        actual_decision_extractor: Given (prior_verdict, pipeline_result),
            return 0 (cosmetic — verdict unchanged) or 1 (substantive —
            verdict changed). Encapsulates the verdict-comparison logic
            without coupling the shadow wrapper to any specific pipeline
            shape.
        fixture_id: optional fixture identifier for traceability.
        ledger_path: optional override; defaults to the canonical
            apps/rtb-manual location.
        skip_pipeline: STRUCTURALLY FORBIDDEN. If set to True, this function
            raises `ShadowModeBypassError`. The parameter exists ONLY to
            make accidental misuse fail loudly (rather than silently
            because a misnamed argument was ignored).

    Returns:
        A ShadowInvocationRecord. The record's `agreed` field is True iff
        the switch decision matched the pipeline's actual decision.

    Raises:
        ShadowModeBypassError: if `skip_pipeline=True`.
        Any exception propagated from `run_pipeline_fn`.
    """
    if skip_pipeline:
        # Hard fail. Per plan §S11: shadow mode CANNOT replace pipeline
        # execution. Make this structurally impossible via the API contract.
        raise ShadowModeBypassError(
            "Refusing to skip pipeline execution in shadow mode. Per plan "
            "§S11, the switch MUST run alongside the full pipeline during "
            "the >=14-day shadow window. Promotion to load-bearing requires "
            "a founder commit flipping switch.LOAD_BEARING_FLAG; until then "
            "no caller may use the switch decision to bypass the pipeline."
        )

    if not callable(run_pipeline_fn):
        raise ValueError(
            f"run_pipeline_fn must be callable, got "
            f"{type(run_pipeline_fn).__name__}"
        )
    if not callable(actual_decision_extractor):
        raise ValueError(
            "actual_decision_extractor must be callable"
        )

    resolved_ledger = ledger_path if ledger_path is not None else _resolve_ledger_path()

    # 1. Invoke the switch. Failures are recorded but never block the pipeline.
    switch_decision: Optional[int] = None
    switch_confidence: Optional[str] = None
    switch_rationale = "(switch unavailable)"
    switch_source: Optional[str] = None
    switch_latency_ms: Optional[int] = None

    try:
        result: SubstantialChangeResult = has_substantially_changed(
            prev_input_hash=prev_input_hash,
            prev_verdict=prev_verdict,
            current_input=current_input,
        )
        switch_decision = result.decision
        switch_confidence = result.confidence
        switch_rationale = result.rationale
        switch_source = result.source
        switch_latency_ms = result.latency_ms
    except SwitchUnavailableError as exc:
        # Fail-loud at the switch surface, but in shadow mode the wrapper
        # absorbs this so the divergence ledger captures the unavailability
        # event. The pipeline still runs unconditionally below.
        switch_rationale = f"SwitchUnavailable: {exc}"
        logging.warning(
            f"Switch unavailable in shadow run (fixture={fixture_id!r}): {exc}"
        )

    # 2. ALWAYS invoke the full pipeline. This is the entire point of
    #    shadow mode. No caller, no flag, no condition can skip this.
    pipeline_start = time.perf_counter()
    pipeline_result = run_pipeline_fn()
    actual_latency_ms = int((time.perf_counter() - pipeline_start) * 1000)

    # 3. Extract the comparable decision from the pipeline result.
    actual_decision = actual_decision_extractor(prev_verdict, pipeline_result)
    if actual_decision not in (0, 1):
        raise ValueError(
            f"actual_decision_extractor must return 0 or 1, got "
            f"{actual_decision!r}"
        )

    # 4. Compute agreement (only meaningful if the switch produced a decision).
    agreed = (switch_decision is not None) and (switch_decision == actual_decision)

    # 5. Build + persist the record.
    record = ShadowInvocationRecord(
        schema_version=SHADOW_SCHEMA_VERSION,
        timestamp=_isoformat_utc(time.time()),
        fixture_id=fixture_id,
        prev_hash=prev_input_hash,
        current_hash=_hash_current_input(current_input),
        switch_decision=switch_decision,
        switch_confidence=switch_confidence,
        switch_rationale=switch_rationale,
        switch_source=switch_source,
        switch_latency_ms=switch_latency_ms,
        actual_decision=actual_decision,
        actual_latency_ms=actual_latency_ms,
        agreed=agreed,
        pipeline_result=pipeline_result,
    )

    _ensure_ledger_header(resolved_ledger)
    _append_ledger_row(resolved_ledger, record.to_ledger_dict())

    return record


# ─────────────────────────────────────────────────────────────────────────────
# Test-only helpers
# ─────────────────────────────────────────────────────────────────────────────


_test_internals = {
    "default_ledger_path": _default_ledger_path,
    "resolve_ledger_path": _resolve_ledger_path,
    "ensure_ledger_header": _ensure_ledger_header,
    "append_ledger_row": _append_ledger_row,
    "isoformat_utc": _isoformat_utc,
    "SHADOW_SCHEMA_VERSION": SHADOW_SCHEMA_VERSION,
}
