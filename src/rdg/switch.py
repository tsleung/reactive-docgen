"""
RDG LLM-Switch Predicate (S11) — substantial-change classifier.

Spec: a consumer repo §S11
Plan reference: a consumer repo (S10 regression anchor)
Story: docs/coordination/items/wo-task-codification-doctrine-s11-rdg-llm-switch-predicate.work.json

What this module does
---------------------
Given a `(prev_input_hash, prev_verdict, current_input)` triple, ask a CHEAP
Sonnet 4.6 model:

  "Has this facet changed substantially enough to re-run the upstream RDG
   pipeline? Answer 0 (cosmetic — skip) or 1 (substantive — re-run)."

The switch GATES expensive Opus pipeline runs. Misclassification cost is
asymmetric:
  - false negative (says cosmetic when actually substantive)  → audit silently
    stale until the next genuine substantive change forces a re-run; AUDIT
    VERDICT IS WRONG IN THE INTERIM. This is the dangerous failure mode.
  - false positive (says substantive when actually cosmetic) → wastes one
    Opus call. Cheap, recoverable.

The switch is therefore a HIGH-RISK component. Per plan §S11 and Convention 6:
  * shadow mode is MANDATORY for >=14 days before the switch becomes load-bearing
  * promotion gate: `divergence_rate < 0.05 AND total_invocations >= 20 AND
                     shadow_duration_days >= 14`
  * post-promotion, shadow re-fires quarterly OR on Sonnet model bump.

PROMOTION IS HUMANGATED. This module ships a `LOAD_BEARING_FLAG` constant set
to False. Flipping it to True requires a founder commit. Per plan §Founder
doctrine: *"x graduation is never inscope for x exploration."* — equivalent
applies here: switch promotion is never in-scope for switch development.

Composition
-----------
The switch composes on top of the existing MD5(rendered_template) byte-equality
cache at `gemini.py:get_cache_key()`. The byte-equality cache remains the FIRST
LINE — if `prev_input_hash == hash(current_input)`, no LLM call is made. The
switch only fires when the byte-cache MISSES but the diff might still be
cosmetic.

Fail-loud guarantee
-------------------
NO silent defaults. If the Claude CLI is unavailable AND the byte cache cannot
be consulted (which never happens — byte equality is pure-Python and always
available), this module raises `SwitchUnavailableError` with verbatim context.
Per RtB Boundary Rule (CLAUDE_ENG.md §10): defaults acceptable at boundaries
only; internal pipeline flow must fail loudly.

API
---
```python
from rdg.switch import has_substantially_changed, SubstantialChangeResult

result = has_substantially_changed(
    prev_input_hash="abc123...",  # md5 of prior input
    prev_verdict="PASS",           # prior pipeline verdict (informational)
    current_input="...",           # current rendered template / source
)
# result = SubstantialChangeResult(
#   decision=1,                   # 0 = cosmetic, 1 = substantive
#   confidence="high",            # 'high' | 'medium' | 'low'
#   rationale="introduces ?? fallback in financial-calc path",
#   latency_ms=420,
# )
```
"""

from __future__ import annotations

import hashlib
import logging
import os
import re
import shutil
import subprocess
import time
from dataclasses import dataclass
from typing import Optional


# Config — read env vars directly (instead of `from .config import ...`) so
# this module does NOT pull `python-dotenv` into the import graph. The switch
# is invoked from test contexts that may not have the project's full venv;
# keeping config self-contained means `python3 -c "from rdg.switch import ..."`
# succeeds anywhere Python 3 is on PATH. This mirrors the discipline that
# claude.py uses no third-party imports.
CLAUDE_CLI_PATH = os.environ.get("CLAUDE_CLI_PATH", "claude")
CLAUDE_CLI_TIMEOUT_SECONDS = int(os.environ.get("CLAUDE_CLI_TIMEOUT_SECONDS", "600"))


# Self-contained CLI resolver. We deliberately do NOT `from . import claude as
# claude_module`; the existing claude.py imports rdg.config which requires
# python-dotenv, which is overkill for the switch's needs. The pattern is the
# same shape as claude.py:_resolve_cli, intentionally — see test_switch.py for
# the mocking surface.
_resolved_cli_path: Optional[str] = None


def _resolve_cli() -> Optional[str]:
    """Locate the Claude CLI binary on PATH. Cached. Returns None when absent.

    Test surface: tests mock `switch._resolve_cli` to return either a fake path
    (for end-to-end mocking with subprocess.run also mocked) or None (to
    verify SwitchUnavailableError is raised).
    """
    global _resolved_cli_path
    if _resolved_cli_path is not None:
        return _resolved_cli_path
    path = shutil.which(CLAUDE_CLI_PATH)
    if path is not None:
        _resolved_cli_path = path
    return path


# ─────────────────────────────────────────────────────────────────────────────
# Constants
# ─────────────────────────────────────────────────────────────────────────────

# Default Sonnet model alias for the switch. Kept SEPARATE from
# CLAUDE_CLI_MODEL (default "sonnet") so that operators can pin a specific
# Sonnet version for the switch without affecting the pipeline's main calls.
DEFAULT_SWITCH_MODEL = "claude-sonnet-4-6"

# Hard ceiling on switch latency. Per dispatch prompt: "this is supposed to be
# cheap." If a single switch call exceeds this, it is a regression — the
# switch should respond in well under a second.
SWITCH_LATENCY_BUDGET_MS = 5_000

# Promotion flag — HUMAN-GATED. NEVER flip this in autonomous code. Per plan
# §S11 + §Risk concentration, switching this to True requires:
#   1. >=14 days of shadow-mode data
#   2. divergence_rate < 0.05 across >=20 invocations
#   3. founder-committed change to this constant
#
# When False, the shadow wrapper runs the switch alongside the full pipeline
# but NEVER uses the switch decision to skip work.
LOAD_BEARING_FLAG: bool = False


# ─────────────────────────────────────────────────────────────────────────────
# Prompt template — kept short for cheapness
# ─────────────────────────────────────────────────────────────────────────────

# Sonnet receives this template. Designed to be ~10 lines, returning a
# structured single-line decision. The model is asked to emit a strict
# `DECISION: 0|1` line followed by a one-line rationale, so the parser is
# deterministic.
_SWITCH_PROMPT_TEMPLATE = """You are a CHEAP gatekeeper for an expensive code/doc audit pipeline.

Given a CHANGE to source content, decide if the change is substantive enough that an upstream audit (which catches code-health / doctrine violations) MUST be re-run. Be CONSERVATIVE: when uncertain, choose substantive (1).

DECISION RULES
- Pure whitespace / formatting / line-break / import-reorder: NOT substantive (0).
- Comment-only edits with no code change: NOT substantive (0).
- Metadata-only edits (Last Updated date bumps, version bumps without body change): NOT substantive (0).
- Variable renames with no semantic change: NOT substantive (0).
- ANY change to code logic, control flow, error handling, fallback patterns: SUBSTANTIVE (1).
- Net-new functions, net-new exports, net-new code surface: SUBSTANTIVE (1).
- Doctrine body rewrites (changing what the doctrine says): SUBSTANTIVE (1).
- Anything that could change an audit verdict: SUBSTANTIVE (1).

OUTPUT FORMAT (strict — first line MUST be DECISION):
DECISION: 0
RATIONALE: <one short sentence>

OR:
DECISION: 1
RATIONALE: <one short sentence>

PRIOR INPUT HASH (for context only — do not over-index): {prev_hash}
PRIOR VERDICT (for context only): {prev_verdict}

CURRENT INPUT:
---
{current_input}
---

Respond with the strict two-line format only."""


# ─────────────────────────────────────────────────────────────────────────────
# Result types + errors
# ─────────────────────────────────────────────────────────────────────────────


Confidence = str  # 'high' | 'medium' | 'low'


@dataclass(frozen=True)
class SubstantialChangeResult:
    """Switch verdict + provenance.

    Attributes:
        decision: 0 = cosmetic (skip pipeline), 1 = substantive (re-run).
        confidence: 'high' if decision was made via Claude with a clear
            DECISION-line response; 'medium' if parsing was lenient; 'low'
            if we fell back to byte-equality OR ambiguous parsing.
        rationale: one-line natural-language rationale.
        latency_ms: time taken by the switch call.
        source: 'claude' | 'byte-cache-equality' — which mechanism produced
            the decision.
    """

    decision: int  # 0 or 1
    confidence: Confidence
    rationale: str
    latency_ms: int
    source: str

    def __post_init__(self) -> None:
        # Fail loud on invalid construction. No silent coercion.
        if self.decision not in (0, 1):
            raise ValueError(
                f"SubstantialChangeResult.decision must be 0 or 1, got {self.decision!r}"
            )
        if self.confidence not in ("high", "medium", "low"):
            raise ValueError(
                f"SubstantialChangeResult.confidence must be one of "
                f"('high', 'medium', 'low'), got {self.confidence!r}"
            )
        if self.source not in ("claude", "byte-cache-equality"):
            raise ValueError(
                f"SubstantialChangeResult.source must be one of "
                f"('claude', 'byte-cache-equality'), got {self.source!r}"
            )


class SwitchUnavailableError(RuntimeError):
    """Raised when no mechanism can decide substantial-change.

    Per RtB fail-loud doctrine: when the switch is unable to render any
    verdict (neither Claude CLI nor byte-equality cache can answer), we do
    NOT silently default to "substantive" or "cosmetic". The caller is told
    explicitly so they can choose how to proceed (typically: fall back to
    running the full pipeline unconditionally).
    """


# ─────────────────────────────────────────────────────────────────────────────
# Byte-equality fast path (composes on top of existing gemini.py cache)
# ─────────────────────────────────────────────────────────────────────────────


def _hash_current_input(current_input: str) -> str:
    """Compute the same MD5 the gemini.py cache uses.

    Composes on top of the existing cache contract at
    `gemini.py:get_cache_key()` so the switch's byte-equality fast path
    reaches the same conclusion the cache would.
    """
    return hashlib.md5(current_input.encode()).hexdigest()


def _byte_equality_short_circuit(
    prev_input_hash: str, current_input: str
) -> Optional[SubstantialChangeResult]:
    """Return a 'cosmetic' verdict if input bytes are unchanged.

    This is the cheapest possible decision: if the current input hashes
    identically to the prior input, NOTHING has changed — not even
    whitespace — and the audit cannot possibly produce a different verdict.
    Returns None when the hashes differ (we need the Claude switch).
    """
    if not isinstance(prev_input_hash, str) or not prev_input_hash:
        # Boundary input — empty or non-string prev hash means "no prior",
        # which is a substantive event (the switch must be consulted) but
        # the byte-equality path cannot conclude. Return None to defer.
        return None
    current_hash = _hash_current_input(current_input)
    if current_hash == prev_input_hash:
        return SubstantialChangeResult(
            decision=0,
            confidence="high",
            rationale="Byte-identical input — no audit change possible.",
            latency_ms=0,
            source="byte-cache-equality",
        )
    return None


# ─────────────────────────────────────────────────────────────────────────────
# Claude CLI invocation (mirrors claude.py:call_claude pattern)
# ─────────────────────────────────────────────────────────────────────────────


_DECISION_LINE_RE = re.compile(r"^\s*DECISION\s*:\s*([01])\s*$", re.IGNORECASE)
_RATIONALE_LINE_RE = re.compile(r"^\s*RATIONALE\s*:\s*(.+?)\s*$", re.IGNORECASE)


def _parse_claude_response(raw: str) -> tuple[int, str, Confidence]:
    """Parse a strict 2-line response from Sonnet.

    Returns (decision, rationale, confidence). Raises ValueError if no
    valid DECISION line can be located — per fail-loud doctrine, malformed
    output is not silently coerced.
    """
    if not raw or not raw.strip():
        raise ValueError("Empty Claude response")

    decision: Optional[int] = None
    rationale: Optional[str] = None
    confidence: Confidence = "high"

    lines = raw.splitlines()
    for line in lines:
        m = _DECISION_LINE_RE.match(line)
        if m is not None and decision is None:
            decision = int(m.group(1))
            continue
        r = _RATIONALE_LINE_RE.match(line)
        if r is not None and rationale is None:
            rationale = r.group(1).strip()

    if decision is None:
        # Lenient second pass: maybe Sonnet prefixed with explanation.
        # Look anywhere in the response for a bare "DECISION: 0/1".
        for line in lines:
            m = _DECISION_LINE_RE.search(line)
            if m is not None:
                decision = int(m.group(1))
                confidence = "medium"
                break

    if decision is None:
        raise ValueError(
            f"Could not parse a DECISION line from Claude response. "
            f"Raw response: {raw[:400]!r}"
        )

    if rationale is None:
        rationale = "(no rationale in model output)"
        confidence = "low"

    return decision, rationale, confidence


def _invoke_claude_switch(
    prev_hash: str,
    prev_verdict: str,
    current_input: str,
    model: str,
    timeout_seconds: int,
) -> tuple[int, str, Confidence, int]:
    """Invoke the Claude CLI for the switch decision.

    Returns (decision, rationale, confidence, latency_ms). Raises
    `SwitchUnavailableError` when the Claude CLI is missing or fails.
    """
    cli = _resolve_cli()
    if cli is None:
        raise SwitchUnavailableError(
            f"Claude CLI not available at PATH (looked for "
            f"{CLAUDE_CLI_PATH!r}). Install Claude Code or set "
            f"CLAUDE_CLI_PATH to a valid binary location."
        )

    prompt = _SWITCH_PROMPT_TEMPLATE.format(
        prev_hash=prev_hash or "(none)",
        prev_verdict=prev_verdict or "(none)",
        current_input=current_input,
    )

    start = time.perf_counter()
    try:
        # NOTE: deliberately NO `--effort` here, unlike claude.py::build_argv.
        # The switch is a binary changed/not-changed classification and is
        # non-verdict-bearing, so MODEL_ROUTING's effort floor does not reach
        # it; raising effort would buy nothing and cost latency on a call whose
        # whole contract is "cheap" (see the timeout message below). Leave it
        # inheriting the CLI default — this omission is a decision, not a gap.
        result = subprocess.run(
            [cli, "--print", "--model", model],
            input=prompt,
            capture_output=True,
            text=True,
            timeout=timeout_seconds,
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        raise SwitchUnavailableError(
            f"Claude CLI timed out after {timeout_seconds}s on switch call. "
            f"The switch is supposed to be cheap; treat persistent timeouts "
            f"as a regression."
        ) from exc

    latency_ms = int((time.perf_counter() - start) * 1000)

    if result.returncode != 0:
        stderr_tail = (result.stderr or "").strip()[-500:]
        raise SwitchUnavailableError(
            f"Claude CLI exited {result.returncode} on switch call. "
            f"stderr tail: {stderr_tail!r}"
        )

    try:
        decision, rationale, confidence = _parse_claude_response(result.stdout)
    except ValueError as exc:
        # Re-raise as SwitchUnavailableError so the caller's recovery path
        # treats a malformed response the same as a missing CLI: fall back to
        # running the full pipeline unconditionally rather than silently
        # picking a default.
        raise SwitchUnavailableError(
            f"Failed to parse Claude switch response: {exc}"
        ) from exc

    return decision, rationale, confidence, latency_ms


# ─────────────────────────────────────────────────────────────────────────────
# Public API
# ─────────────────────────────────────────────────────────────────────────────


def has_substantially_changed(
    prev_input_hash: str,
    prev_verdict: str,
    current_input: str,
    *,
    model: str = DEFAULT_SWITCH_MODEL,
    timeout_seconds: int = CLAUDE_CLI_TIMEOUT_SECONDS,
) -> SubstantialChangeResult:
    """Decide whether the current input is substantively different from the prior input.

    First tries byte-equality short-circuit (free, always works). On miss,
    invokes the Claude CLI with a CHEAP Sonnet prompt that returns a 0/1
    decision + one-line rationale.

    Raises:
        SwitchUnavailableError: when neither the byte-equality fast path nor
            the Claude CLI can render a verdict. Per RtB fail-loud doctrine,
            callers MUST handle this explicitly — typically by running the
            full pipeline unconditionally rather than silently defaulting.
        ValueError: on programmer error in argument types.

    Returns:
        SubstantialChangeResult with `decision`, `confidence`, `rationale`,
        `latency_ms`, and `source` fields.

    Note: this function is INTENTIONALLY synchronous and NEVER returns a
    silent default. If you need a fallback ("run pipeline anyway on switch
    failure"), wrap this call yourself — the wrapper at switch_shadow.py
    shows the recommended pattern.
    """
    if not isinstance(current_input, str):
        raise ValueError(
            f"current_input must be str, got {type(current_input).__name__}"
        )
    if not isinstance(prev_input_hash, str):
        raise ValueError(
            f"prev_input_hash must be str, got {type(prev_input_hash).__name__}"
        )
    if not isinstance(prev_verdict, str):
        raise ValueError(
            f"prev_verdict must be str, got {type(prev_verdict).__name__}"
        )

    # 1. Byte-equality fast path. Always available, zero cost.
    byte_result = _byte_equality_short_circuit(prev_input_hash, current_input)
    if byte_result is not None:
        return byte_result

    # 2. Claude switch. May raise SwitchUnavailableError — the caller decides.
    try:
        decision, rationale, confidence, latency_ms = _invoke_claude_switch(
            prev_hash=prev_input_hash,
            prev_verdict=prev_verdict,
            current_input=current_input,
            model=model,
            timeout_seconds=timeout_seconds,
        )
    except SwitchUnavailableError:
        # Fail loud. Let the exception propagate; do not invent a verdict.
        raise

    return SubstantialChangeResult(
        decision=decision,
        confidence=confidence,
        rationale=rationale,
        latency_ms=latency_ms,
        source="claude",
    )


# ─────────────────────────────────────────────────────────────────────────────
# Test-only helpers (exposed for the test_switch.py regression suite)
# ─────────────────────────────────────────────────────────────────────────────


_test_internals = {
    "hash_current_input": _hash_current_input,
    "byte_equality_short_circuit": _byte_equality_short_circuit,
    "parse_claude_response": _parse_claude_response,
    "SWITCH_PROMPT_TEMPLATE": _SWITCH_PROMPT_TEMPLATE,
    "DECISION_LINE_RE": _DECISION_LINE_RE,
    "RATIONALE_LINE_RE": _RATIONALE_LINE_RE,
}


if __name__ == "__main__":
    # CLI sanity check. Useful for smoke-testing the switch with real input.
    import argparse
    import sys

    parser = argparse.ArgumentParser(
        description=(
            "RDG LLM-Switch CLI smoke test. Reads current input from stdin or "
            "a file and prints the switch decision."
        )
    )
    parser.add_argument("--prev-hash", default="", help="Prior input MD5.")
    parser.add_argument("--prev-verdict", default="", help="Prior pipeline verdict.")
    parser.add_argument(
        "--input-file",
        help="Path to read current_input from. If omitted, reads stdin.",
    )
    parser.add_argument("--model", default=DEFAULT_SWITCH_MODEL)
    args = parser.parse_args()

    if args.input_file:
        with open(args.input_file, "r", encoding="utf-8") as f:
            current = f.read()
    else:
        current = sys.stdin.read()

    try:
        verdict = has_substantially_changed(
            prev_input_hash=args.prev_hash,
            prev_verdict=args.prev_verdict,
            current_input=current,
            model=args.model,
        )
    except SwitchUnavailableError as exc:
        logging.error(f"Switch unavailable: {exc}")
        sys.exit(2)

    print(
        f"decision={verdict.decision} "
        f"confidence={verdict.confidence} "
        f"latency_ms={verdict.latency_ms} "
        f"source={verdict.source}"
    )
    print(f"rationale: {verdict.rationale}")
