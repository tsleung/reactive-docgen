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
"""

import logging
import shutil
import subprocess

from .config import CLAUDE_CLI_PATH, CLAUDE_CLI_MODEL, CLAUDE_CLI_TIMEOUT_SECONDS

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


def call_claude(rendered_template):
    """
    Invoke the claude CLI in non-interactive print mode. Returns the response
    text on success. On FAILURE (raise, timeout, or non-zero CLI exit) returns
    a non-empty error sentinel (see ENGINE_ERROR_SENTINEL / format_engine_error)
    so the caller writes a non-empty error report carrying the actual cause,
    rather than a 0-byte file that hides the failure. Mirrors the contract of
    memoized_gemini_call.

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
    try:
        result = subprocess.run(
            [cli, "--print", "--model", CLAUDE_CLI_MODEL],
            input=rendered_template,
            capture_output=True,
            text=True,
            timeout=CLAUDE_CLI_TIMEOUT_SECONDS,
            check=False,
        )
        if result.returncode != 0:
            stderr_tail = (result.stderr or "").strip()[-500:]
            logging.error(
                f"Claude CLI exited {result.returncode}: {stderr_tail}"
            )
            return format_engine_error(
                "ClaudeCliNonZeroExit",
                f"exit {result.returncode}: {stderr_tail}",
            )
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
