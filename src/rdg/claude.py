"""
Claude API fallback for RDG pipeline.

When Gemini fails (quota exhaustion, billing 429, transient errors), the
pipeline falls back to Claude. The user pays for Claude API directly so this
is a paid path, but it keeps RDG operational instead of producing empty reports.

Set ANTHROPIC_API_KEY in the .env file (alongside GEMINI_API_KEY) to enable.
If unset, the fallback is a no-op and the original Gemini failure surfaces.
"""

import logging
from .config import anthropic_api_key, CLAUDE_FALLBACK_MODEL, MAX_OUTPUT_TOKENS

# Lazy-import: only initialize the Anthropic client if the fallback is configured
# AND actually invoked. Importing the SDK at module load fails for users without
# the package installed, which would break Gemini-only workflows.
_client = None


def _get_client():
    global _client
    if _client is not None:
        return _client
    if not anthropic_api_key:
        return None
    try:
        import anthropic
        _client = anthropic.Anthropic(api_key=anthropic_api_key)
        logging.info(f"Claude fallback configured: {CLAUDE_FALLBACK_MODEL}")
        return _client
    except ImportError:
        logging.error(
            "Claude fallback requested but `anthropic` package is not installed. "
            "Run: pip install anthropic"
        )
        return None
    except Exception as e:
        logging.error(f"Claude fallback configuration failed: {e}")
        return None


def is_available():
    """True if Claude fallback is configured and ready."""
    return _get_client() is not None


def call_claude(rendered_template):
    """
    Call Claude with the rendered template. Returns the response text on
    success, empty string on failure. Mirrors the contract of memoized_gemini_call.
    """
    client = _get_client()
    if client is None:
        return ""
    try:
        message = client.messages.create(
            model=CLAUDE_FALLBACK_MODEL,
            max_tokens=MAX_OUTPUT_TOKENS,
            messages=[{"role": "user", "content": rendered_template}],
        )
        # Concatenate all text blocks (Claude can return multiple in principle)
        parts = [block.text for block in message.content if hasattr(block, "text")]
        return "".join(parts)
    except Exception as e:
        logging.error(f"Claude API call failed: {e}")
        return ""
