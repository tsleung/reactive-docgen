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
"""

import json
import logging
import os
import sys
from datetime import datetime, timezone

_logger = logging.getLogger("rdg")
_log_file_attached = False


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
