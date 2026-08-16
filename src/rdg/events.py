"""Structured step events — the conventional task-queue answer to "how far has this run got?"

Opt-in and additive: with RDG_EVENTS=jsonl set, the engine emits one JSON object per line on
STDERR at each step boundary (stdout stays untouched — it may carry content). Without the env
var, nothing is emitted and nothing else changes. The shape follows ninja/cargo-style progress
and Celery-style state: a live reader gets progress; a persisted stream gets history — including
which files each step wrote, so artifact origin is the historical read of the same events.

Human-readable lines ride the stock ``logging`` module (logger ``rdg``): events are mirrored at
DEBUG, and RDG_LOG_FILE attaches a FileHandler so a run can keep a plain log beside the machine
stream. Neither env var set → both features dormant.

Event shape (all step events):
    {"ev": "step_start", "i": 3, "n": 9, "dest": "out/x.md", "formula": "CREATEFILE", "ts": "..."}
    {"ev": "step_end",   "i": 3, "n": 9, "dest": "out/x.md", "formula": "CREATEFILE",
     "ok": true, "wrote": ["out/x.md"], "ts": "..."}

``wrote`` lists the paths the step actually wrote — on failure that is still the destination
(the engine writes ## ERROR bytes there), with ``ok`` false so a consumer distinguishes created
content from recorded failure.

Primitive events (one per PROVIDER CALL, not per step — see ``emit_primitive``) ride the same
opt-in gate and the same ``ev`` envelope, and name what a model invocation actually ran with:
    {"ev": "primitive", "phase": "attempt", "formula": "GEMINIPROMPT",
     "model": "gemini-3-flash-preview", "effort": "high", "backend": "gemini",
     "timeout_s": null, "ts": "..."}

Every event carries dispatch facts only — never prompt text, file contents, absolute paths, or
credentials.
"""

import contextvars
import json
import logging
import os
import sys
from datetime import datetime, timezone

_logger = logging.getLogger("rdg")
_log_file_attached = False

# The .rdg formula a provider call is being made for. Set by the shared model path in
# functions.py; read by whichever backend actually runs (see formula_context).
_FORMULA = contextvars.ContextVar("rdg_primitive_formula", default=None)


def _ensure_log_file() -> None:
    global _log_file_attached
    if _log_file_attached:
        return
    log_path = os.environ.get("RDG_LOG_FILE")
    if log_path:
        handler = logging.FileHandler(log_path)
        handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
        _logger.addHandler(handler)
        _logger.setLevel(logging.DEBUG)
    _log_file_attached = True


def events_enabled() -> bool:
    return os.environ.get("RDG_EVENTS") == "jsonl"


def emit(ev: str, **fields) -> None:
    """Emit one event. No-op unless RDG_EVENTS=jsonl; mirrored to the ``rdg`` logger at DEBUG."""
    _ensure_log_file()
    payload = {"ev": ev, **fields, "ts": datetime.now(timezone.utc).isoformat()}
    line = json.dumps(payload, separators=(",", ":"))
    _logger.debug("event %s", line)
    if events_enabled():
        print(line, file=sys.stderr, flush=True)


def formula_context(formula: str):
    """Name the .rdg formula on whose behalf the next provider call is made.

    The label cannot ride the call itself: the provider entrypoint is memoised on
    (prompt, model, effort), and adding a fourth argument would split that cache by formula so two
    formulas asking the identical question would each pay for it. A ContextVar is per-thread, so
    the RDG_JOBS wave runner's concurrent steps each see their own label, and the alternative —
    letting the label default to the backend — would print CLAUDE for what is really a GEMINIPROMPT
    step and send a reader looking for a formula their .rdg does not contain.

    Used as a context manager: ``with formula_context("SUMMARIZE"): ...``
    """
    return _FormulaScope(formula)


class _FormulaScope:
    def __init__(self, formula):
        self._formula = formula
        self._token = None

    def __enter__(self):
        self._token = _FORMULA.set(self._formula)
        return self

    def __exit__(self, *exc):
        _FORMULA.reset(self._token)
        return False


def emit_primitive(*, model, effort, backend, timeout_s=None, formula=None,
                   phase="attempt", **extra) -> None:
    """Emit one line describing a model invocation, immediately BEFORE it is made.

    Founder 2026-08-16: *"we should have more observability into what is actually occurring in
    terms of primitives, at least in a log or somewhere."* The step events above say which formula
    ran; this says what it actually ran WITH. The defaults downstream ran invisibly for days
    precisely because nothing recorded the parameters.

    Same envelope as every other event — ``ev`` is the discriminator and the kind is its VALUE, so
    one reader dispatches on one key and a new kind needs no new parsing branch::

        {"ev":"primitive","phase":"attempt","formula":"GEMINIPROMPT","model":"opus",
         "effort":"max","backend":"claude","timeout_s":600,"ts":"…"}

    ``phase`` is "attempt", stated rather than implied, so a later completion event carrying usage,
    cost or a session id extends the same record type instead of breaking its schema.

    ONE record per PROVIDER CALL, not per step: a run that falls back from Gemini to Claude
    honestly emits two. A cache hit emits none, because no call was made — a line for a call that
    did not happen is the phantom this engine refuses in its artifacts.

    RELATION TO THE CONSUMER TWIN. rtb-manual's external CLAUDECODE formula
    (`dcc/rtb-pic/rdg/formulas/claude_code.py`) emits the same record and is where the shape comes
    from, but it is NOT identical and the differences are deliberate: it writes UNCONDITIONALLY,
    this one is gated on the RDG_EVENTS opt-in (founder 2026-08-16 — engine-side logging is
    optional, and a consumer that never asked for a machine stream keeps a clean stderr; the
    downstream runner arms RDG_EVENTS=jsonl on every spawn, so it loses nothing). It also carries
    `workdir`, and this one does not: an absolute filesystem path is a fact about the operator's
    machine, and this engine is open source.

    NEGATIVE CONTRACT — events carry dispatch parameters only. Never prompt text, never file
    contents, never absolute paths, never credentials. Anything a reader might paste into an issue
    must stay safe to paste.
    """
    _ensure_log_file()
    payload = {
        "ev": "primitive",
        "phase": phase,
        "formula": formula or _FORMULA.get() or backend.upper(),
        "model": model,
        "effort": effort,
        "backend": backend,
        **extra,
        "timeout_s": timeout_s,
        "ts": datetime.now(timezone.utc).isoformat(),
    }
    line = json.dumps(payload, separators=(",", ":"))
    _logger.debug("event %s", line)
    if events_enabled():
        # ONE write, not print(): print emits the text and the newline separately, and the
        # RDG_JOBS wave runner has several steps writing to this stream at once — a split write
        # is where two JSON objects end up on one line and a reader loses both.
        sys.stderr.write(line + "\n")
        sys.stderr.flush()
