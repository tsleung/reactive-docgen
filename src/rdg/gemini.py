import google.generativeai as genai
import logging
import hashlib
import json
import os
from functools import lru_cache
from .config import api_key, CACHE_DIR, RDG_PRIMARY
from . import claude as claude_fallback


# When RDG_PRIMARY=claude, skip the Gemini SDK configuration entirely —
# Gemini won't be called, no API key required. This lets users with only
# Claude Code installed run RDG without provisioning a Gemini billing
# account.
if RDG_PRIMARY == "claude":
    logging.info("RDG_PRIMARY=claude — Gemini SDK skipped; all calls route to Claude CLI.")
    if not claude_fallback.is_available():
        logging.error("RDG_PRIMARY=claude requires the `claude` CLI on PATH. Install Claude Code or unset RDG_PRIMARY.")
        exit(1)
    model = None  # not used in claude-primary mode
elif api_key:
    try:
        genai.configure(api_key=api_key)
        generation_config = {
        "temperature": 0.667,
        "top_p": 0.6,
        "top_k": 20,
        # "max_output_tokens": 64192,
        "response_mime_type": "text/plain",
        }
        model = genai.GenerativeModel(
            # model_name="gemini-1.5-pro",
            # model_name="gemini-1.5-flash",  # 404 on this API key (auth not granted)
            # model_name="gemini-2.0-flash-exp",  # 404 on v1beta in this SDK version
            # model_name="gemini-2.5-pro",
            model_name="gemini-3-flash-preview",  # primary; falls back to Claude on quota/billing errors
            generation_config=generation_config,
        )
        logging.info("Gemini API configured successfully.")
    except Exception as e:
        logging.error(f"Gemini API configuration failed: {e}")
        exit(1)
else:
    logging.error("GEMINI_API_KEY environment variable not set.")
    exit(1)


@lru_cache(maxsize=None)
def memoized_gemini_call(rendered_template):
    """
    Routing:
    - RDG_PRIMARY=claude (default off): skip Gemini, call Claude CLI directly.
      Use case: avoid Gemini billing when Claude Code subscription is paid.
    - Otherwise (default): try Gemini first; on any failure (quota, billing,
      transient error), fall back to Claude if the `claude` CLI is available.

    Returns "" only if all configured paths fail. Cache key is the rendered
    template, so a successful Claude response is cached identically to a
    Gemini response.
    """
    if RDG_PRIMARY == "claude":
        # Direct route: no Gemini attempt at all. Avoids quota errors,
        # avoids any billing surface, single-LLM provenance for the run.
        claude_response = claude_fallback.call_claude(rendered_template)
        if claude_response:
            # On claude failure this is a non-empty RDG-ENGINE-ERROR sentinel
            # (not raw model text) — it surfaces here so the caller writes the
            # cause into the report instead of a 0-byte file.
            return claude_response
        # Reached ONLY on a genuine empty response with NO exception. The
        # caller's empty-file detection / 0-byte audit covers this case.
        logging.error("Claude CLI returned empty response (RDG_PRIMARY=claude)")
        return ""

    gemini_response = ""
    gemini_error = None
    try:
        chat_session = model.start_chat(history=[])
        response = chat_session.send_message(rendered_template)
        gemini_response = response.text
        if gemini_response:
            return gemini_response
    except Exception as e:
        gemini_error = e
        logging.error(f"Gemini API call failed: {e}")

    # Fallback path: Claude. Triggered on Gemini exception OR empty Gemini response.
    if claude_fallback.is_available():
        reason = f"exception: {gemini_error}" if gemini_error else "empty response"
        logging.info(f"Falling back to Claude ({reason})")
        claude_response = claude_fallback.call_claude(rendered_template)
        if claude_response:
            # On claude failure this is a non-empty RDG-ENGINE-ERROR sentinel —
            # the caller writes it to the report so the cause is visible.
            return claude_response
        logging.error("Claude fallback also returned empty response")

    # If Gemini RAISED, surface that exception as a non-empty sentinel rather
    # than swallowing it to "". Only when there was NO exception (genuine empty
    # response, no available/successful fallback) do we return "" and let the
    # caller's empty-file detection trigger.
    if gemini_error is not None:
        return claude_fallback.format_engine_error(
            type(gemini_error).__name__, str(gemini_error)
        )

    return gemini_response  # "" — genuine empty (no exception); empty-file detection triggers


def get_cache_key(rendered_template):
    return hashlib.md5(rendered_template.encode()).hexdigest()


def load_from_cache(cache_key):
    cache_file = os.path.join(CACHE_DIR, f"{cache_key}.json")
    try:
        with open(cache_file, 'r') as f:
            data = json.load(f)
            return data["request"], data["response"]
    except (FileNotFoundError, json.JSONDecodeError):
        return None, None


def save_to_cache(cache_key, request, response):
    cache_file = os.path.join(CACHE_DIR, f"{cache_key}.json")
    try:
        with open(cache_file, 'w') as f:
            json.dump({"request": request, "response": response}, f)
    except Exception as e:
        logging.error(f"Error saving to cache '{cache_file}': {e}")