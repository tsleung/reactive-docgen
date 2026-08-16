from google import genai
from google.genai import types
import logging
import hashlib
import json
import os
from functools import lru_cache
from .config import (
    api_key,
    CACHE_DIR,
    CLAUDE_CLI_MODEL,
    RDG_PRIMARY,
    cache_identity,
    resolve_gemini_params,
    validate_effort,
)
from . import claude as claude_fallback
from .events import emit_primitive


# The default model id lives in ONE place, config.GEMINI_MODEL (env RDG_GEMINI_MODEL, overridden
# per step by `model=`). A second copy here is how a run and its own configuration end up
# disagreeing about which model answered.

# effort -> Gemini thinking level. The SDK offers two mechanisms (types.ThinkingConfig):
# `thinking_budget`, an integer token count, and `thinking_level`, an enum. We map to
# thinking_level:
#
#   - it is the mechanism of the model family this engine pins (Gemini 3; thinking_budget is the
#     2.5-era control), and
#   - a level ladder maps onto a level ladder without inventing numbers. The SDK states outright
#     that budget "default values and allowed ranges are model dependent", so any fixed
#     five-rung token table would be a number this engine made up and wrong for some model.
#
# The engine ladder has five rungs and Gemini's has four (MINIMAL/LOW/MEDIUM/HIGH), so the map is
# NAME-PRESERVING and SATURATES at the top: asking for `high` gets HIGH, and the two rungs above it
# also get HIGH because that is Gemini's ceiling. Name-preserving is the deliberate half — a log
# line reading effort=high must not mean MEDIUM. MINIMAL is consequently unreachable; the ladder
# has no rung below `low`, and inventing one would make `low` mean two different things across
# backends. Absent effort sends NO thinking config at all and the provider's own default applies.
EFFORT_THINKING_LEVEL = {
    "low": types.ThinkingLevel.LOW,
    "medium": types.ThinkingLevel.MEDIUM,
    "high": types.ThinkingLevel.HIGH,
    "xhigh": types.ThinkingLevel.HIGH,
    "max": types.ThinkingLevel.HIGH,
}

# When RDG_PRIMARY=claude, skip the Gemini SDK configuration entirely —
# Gemini won't be called, no API key required. This lets users with only
# Claude Code installed run RDG without provisioning a Gemini billing
# account.
if RDG_PRIMARY == "claude":
    logging.info("RDG_PRIMARY=claude — Gemini SDK skipped; all calls route to Claude CLI.")
    if not claude_fallback.is_available():
        logging.error("RDG_PRIMARY=claude requires the `claude` CLI on PATH. Install Claude Code or unset RDG_PRIMARY.")
        exit(1)
    client = None  # not used in claude-primary mode
    generation_config = None
elif api_key:
    try:
        client = genai.Client(api_key=api_key)
        generation_config = types.GenerateContentConfig(
            temperature=0.667,
            top_p=0.6,
            top_k=20,
            # max_output_tokens=64192,
            response_mime_type="text/plain",
        )
        logging.info("Gemini API configured successfully.")
    except Exception as e:
        logging.error(f"Gemini API configuration failed: {e}")
        exit(1)
else:
    logging.error("GEMINI_API_KEY environment variable not set.")
    exit(1)


def config_for(effort):
    """The GenerateContentConfig for one call.

    `effort` None returns the module-level config UNCHANGED — no thinking configuration is sent
    and Gemini's own default applies, which is what "the step did not ask" must mean. Otherwise a
    per-call copy carries the mapped thinking level; the base config is never mutated, so two
    concurrent steps (RDG_JOBS waves) cannot see each other's effort.
    """
    if effort is None or generation_config is None:
        return generation_config
    return generation_config.model_copy(update={
        "thinking_config": types.ThinkingConfig(thinking_level=EFFORT_THINKING_LEVEL[effort]),
    })


@lru_cache(maxsize=None)
def memoized_gemini_call(rendered_template, model=None, effort=None):
    """
    Routing:
    - RDG_PRIMARY=claude (default off): skip Gemini, call Claude CLI directly.
      Use case: avoid Gemini billing when Claude Code subscription is paid.
    - Otherwise (default): try Gemini first; on any failure (quota, billing,
      transient error), fall back to Claude if the `claude` CLI is available.

    `model` / `effort` are the calling step's standard parameters; None means the step named
    none, so this run's configured default applies. They are passed RAW (unresolved) so each
    backend can resolve them by its OWN rule: `effort` is a provider-neutral level and follows the
    call wherever it goes, while `model` is a provider-scoped id — a Gemini→Claude fallback
    therefore uses CLAUDE_CLI_MODEL rather than handing the CLI a model id it cannot honor.

    Memoised on (prompt, model, effort) — the three things that determine the answer. The .rdg
    formula label is NOT among them; it travels on a ContextVar (events.formula_context) so two
    formulas asking the identical question still share one call.

    Returns "" only if all configured paths fail. Cache key is the rendered
    template plus the call identity (see get_cache_key), so a successful Claude
    response is cached identically to a Gemini response.
    """
    # Validated once, for BOTH routes, before either provider is reached. The parser already
    # refuses a bad level at the .rdg line; this covers a direct caller (SUMMARIZE's own prompt
    # path, a test, a REPL) so an invalid effort can never reach a provider that would shrug and
    # run at its default.
    effort = validate_effort(effort, "effort=")

    if RDG_PRIMARY == "claude":
        # Direct route: no Gemini attempt at all. Avoids quota errors,
        # avoids any billing surface, single-LLM provenance for the run.
        claude_response = claude_fallback.call_claude(
            rendered_template, model=model, effort=effort
        )
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
    gemini_model, gemini_effort = resolve_gemini_params(model, effort)
    try:
        emit_primitive(
            model=gemini_model, effort=gemini_effort, backend="gemini", timeout_s=None,
        )
        response = client.models.generate_content(
            model=gemini_model,
            contents=rendered_template,
            config=config_for(gemini_effort),
        )
        gemini_response = response.text
        if gemini_response:
            return gemini_response
    except Exception as e:
        gemini_error = e
        logging.error(f"Gemini API call failed: {e}")

    # Fallback path: Claude. Triggered on Gemini exception OR empty Gemini response.
    # `model` is deliberately NOT forwarded: it named a Gemini model, and this is the Claude
    # backend, which uses its own configured model. `effort` IS forwarded — it is a level, not an
    # id, and the step asked for that level of thinking regardless of who answers. The second
    # primitive event this emits is the honest record that two invocations happened.
    if claude_fallback.is_available():
        reason = f"exception: {gemini_error}" if gemini_error else "empty response"
        # WARNING, not info, and unconditional: the answer is about to come from a different
        # model than the step asked for. A run that silently substitutes the model is the one
        # thing `model=` must never let happen quietly — the level survives the switch, the id
        # cannot.
        logging.warning(
            f"Falling back to Claude ({reason}) — model substituted: "
            f"{gemini_model} -> {CLAUDE_CLI_MODEL} (effort {gemini_effort!r} forwarded unchanged; "
            f"the requested Gemini model id has no meaning to the Claude CLI)"
        )
        claude_response = claude_fallback.call_claude(rendered_template, effort=effort)
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


def get_cache_key(rendered_template, model=None, effort=None):
    """Cache key for one call: the prompt, plus the call identity when it is not the default one.

    A response cached from one model must never be served as another model's answer — that is a
    phantom artifact, and it would make `model=` a claim rather than a fact. The identity suffix
    (config.cache_identity) is EMPTY for the default call, so this returns exactly md5(prompt) as
    it always has and every entry already on disk stays addressable.
    """
    return hashlib.md5((rendered_template + cache_identity(model, effort)).encode()).hexdigest()


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