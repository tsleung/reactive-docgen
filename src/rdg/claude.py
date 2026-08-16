"""
Claude CLI fallback for RDG pipeline.

When Gemini fails (quota exhaustion, billing 429, transient errors), the
pipeline falls back to the local `claude` CLI — the same Claude Code binary
the user is already authenticated against. This avoids needing a separate
ANTHROPIC_API_KEY (which would require a second billing account); the CLI
uses the existing Claude subscription.

Requirements:
- `claude` binary on PATH (https://docs.claude.com/en/docs/claude-code)
- User authenticated (one-time `claude login`)

Configuration:
- CLAUDE_CLI_PATH (optional) — override binary location; defaults to "claude"
- CLAUDE_CLI_MODEL (optional) — model alias (sonnet/opus/haiku); defaults to "sonnet"
- CLAUDE_CLI_TIMEOUT_SECONDS (optional) — per-call timeout; defaults to 600 (10 min)
- CLAUDE_CLI_EFFORT (optional) — reasoning effort (low/medium/high/xhigh/max).
  Unset omits the flag entirely and inherits the CLI default. Validated at
  import in config.py; an invalid value raises rather than degrading silently.

The last two are RUN-level defaults. A single `.rdg` step overrides both with the
standard `model=` / `effort=` parameters, which arrive here as arguments — this is
a model backend, so it takes the same two parameters the model formulas do.
"""

import logging
import shutil
import subprocess

from .config import (
    CLAUDE_CLI_PATH,
    CLAUDE_CLI_MODEL,
    CLAUDE_CLI_TIMEOUT_SECONDS,
    CLAUDE_CLI_EFFORT,
    resolve_claude_params,
)
from .events import emit_primitive

_resolved_path = None
_availability_logged = False

# Non-empty sentinel prefix written into the output file when the LLM call
# FAILS (raises, times out, or the CLI exits non-zero). Returning this string
# instead of "" means the caller writes a non-empty error report carrying the
# actual cause (e.g. "context window exceeded") rather than a 0-byte file that
# hides the failure. The RtB-side audit `audit-rdg-empty-reports.ts` hard-fails
# on 0-byte files; a non-empty sentinel satisfies it AND makes the cause visible.
# This is the EXCEPTION/failure path only — a model that genuinely returns an
# empty response with NO exception still yields "" (see gemini.py).
ENGINE_ERROR_SENTINEL = "RDG-ENGINE-ERROR"


def format_engine_error(exc_type, message):
    """Build the non-empty error sentinel string surfaced into the output file.

    Format: ``RDG-ENGINE-ERROR: <ExceptionType>: <message>`` so both the
    failure class and its detail land in the report.
    """
    return f"{ENGINE_ERROR_SENTINEL}: {exc_type}: {message}"


def _resolve_cli():
    """Find the claude binary on PATH (or at CLAUDE_CLI_PATH). Cached."""
    global _resolved_path, _availability_logged
    if _resolved_path is not None:
        return _resolved_path
    path = shutil.which(CLAUDE_CLI_PATH)
    if path:
        _resolved_path = path
        if not _availability_logged:
            logging.info(
                f"Claude CLI fallback configured: {path} (model: {CLAUDE_CLI_MODEL})"
            )
            _availability_logged = True
    return path


def is_available():
    """True if the claude CLI is installed and discoverable."""
    return _resolve_cli() is not None


def build_argv(cli, model=None, effort=None):
    """Build the print-mode argv: ``--print --model <model>``, plus
    ``--effort <level>`` ONLY when an effort level is configured.

    `model` / `effort` are the step's standard parameters. ``None`` means the
    step did not name one, so this run's configured default applies
    (CLAUDE_CLI_MODEL / CLAUDE_CLI_EFFORT) — resolution lives in config.py so
    both backends resolve by the same rule.

    Omitting the flag when effort is unset everywhere is deliberate — it
    inherits the CLI's own default rather than this engine picking one. Flag
    order (model, then effort) matches spawn-claude.ts so the two dispatch sites
    stay comparable.

    Pure and separately testable: the argv contract is the part worth asserting,
    and it can be checked without spawning a process or making an LLM call.
    """
    model, effort = resolve_claude_params(model, effort)
    argv = [cli, "--print", "--model", model]
    if effort is not None:
        argv += ["--effort", effort]
    return argv


def call_claude(rendered_template, model=None, effort=None):
    """
    Invoke the claude CLI in non-interactive print mode. Returns the response
    text on success. On FAILURE (raise, timeout, or non-zero CLI exit) returns
    a non-empty error sentinel (see ENGINE_ERROR_SENTINEL / format_engine_error)
    so the caller writes a non-empty error report carrying the actual cause,
    rather than a 0-byte file that hides the failure. Mirrors the contract of
    memoized_gemini_call.

    `model` / `effort` are the calling step's standard parameters (None = this
    run's configured default). The .rdg formula the call is made for labels the
    primitive event and arrives on a ContextVar (events.formula_context), so it
    does not become a fourth key on the memoised call above it.

    Uses --print (one-shot, no REPL) and pipes the prompt via stdin to avoid
    argv length limits on long audit prompts.
    """
    cli = _resolve_cli()
    if cli is None:
        # Configuration/availability gap, not a per-call exception. In
        # RDG_PRIMARY=claude mode availability is enforced at import (exit 1);
        # from the Gemini fallback path call_claude is only invoked when
        # is_available() is True. Left as "" — not the exception surface.
        return ""
    resolved_model, resolved_effort = resolve_claude_params(model, effort)
    argv = build_argv(cli, resolved_model, resolved_effort)
    emit_primitive(
        model=resolved_model,
        effort=resolved_effort,
        backend="claude",
        timeout_s=CLAUDE_CLI_TIMEOUT_SECONDS,
    )
    try:
        result = subprocess.run(
            argv,
            input=rendered_template,
            capture_output=True,
            text=True,
            timeout=CLAUDE_CLI_TIMEOUT_SECONDS,
            check=False,
        )
        if result.returncode != 0:
            # BOTH streams. The CLI writes its error payload to STDOUT under
            # `--output-format json`, so a stderr-only tail reported every real
            # failure as "exit 1:" with nothing after the colon — reproduced
            # twice downstream on rtb-runner/graph/migration-report.rdg. The
            # cause was on stdout the whole time, and the report dropped it.
            stderr_tail = (result.stderr or "").strip()[-500:]
            stdout_tail = (result.stdout or "").strip()[-500:]
            detail = f"exit {result.returncode}: {stderr_tail}"
            if stdout_tail:
                detail += f" | stdout: {stdout_tail}"
            logging.error(f"Claude CLI exited {result.returncode}: {detail}")
            return format_engine_error("ClaudeCliNonZeroExit", detail)
        return result.stdout
    except subprocess.TimeoutExpired:
        logging.error(f"Claude CLI timed out after {CLAUDE_CLI_TIMEOUT_SECONDS}s")
        return format_engine_error(
            "subprocess.TimeoutExpired",
            f"Claude CLI timed out after {CLAUDE_CLI_TIMEOUT_SECONDS}s",
        )
    except Exception as e:
        logging.error(f"Claude CLI invocation failed: {e}")
        return format_engine_error(type(e).__name__, str(e))
