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
    text on success, empty string on failure. Mirrors the contract of
    memoized_gemini_call.

    Uses --print (one-shot, no REPL) and pipes the prompt via stdin to avoid
    argv length limits on long audit prompts.
    """
    cli = _resolve_cli()
    if cli is None:
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
            return ""
        return result.stdout
    except subprocess.TimeoutExpired:
        logging.error(f"Claude CLI timed out after {CLAUDE_CLI_TIMEOUT_SECONDS}s")
        return ""
    except Exception as e:
        logging.error(f"Claude CLI invocation failed: {e}")
        return ""
