import os
import logging
from dotenv import load_dotenv

load_dotenv()

LOG_FORMAT = '%(asctime)s - %(levelname)s - %(message)s'
logging.basicConfig(level=logging.INFO, format=LOG_FORMAT)

# Response cache location. Relative by default, which means it lands in whatever directory the
# process happened to start in — so two runs from different working directories silently use
# different caches, and two unrelated runs from the same directory share one. A caller that wants
# the cache scoped to something meaningful (a pipeline, a project) had no way to say so except by
# choosing its cwd, which is a coarse instrument when the cwd is also where relative paths resolve.
#
# The default is unchanged, so existing behaviour is identical when the variable is unset.
CACHE_DIR = os.environ.get("RDG_CACHE_DIR", ".gemini_cache")
os.makedirs(CACHE_DIR, exist_ok=True)

THROTTLE_SECONDS = 1
MAX_OUTPUT_TOKENS = 8000  # Gemini ceiling — applies to Gemini calls only.

api_key = os.environ.get("GEMINI_API_KEY")

# ---------------------------------------------------------------------------
# The effort ladder — ONE vocabulary, every backend
# ---------------------------------------------------------------------------
#
# Founder 2026-08-16: "for all of our rdg formulas though, setting a model and effort should be
# standard if an LLM is involved… we can just make them different parameters, that way model
# switching is simple."
#
# A "standard parameter" that means different words at different formulas is not standard, so the
# ladder is defined ONCE here, above either backend's config, and each backend maps it to its own
# mechanism: the Claude CLI takes it verbatim as `--effort` (below), Gemini maps it to a thinking
# level (gemini.py). Levels are the ones the Claude CLI already publishes, and are mirrored in
# a downstream consumer's own spawn wrapper.
#
# `effort` is provider-NEUTRAL — it is a level, not an id — so it follows a call to whichever
# backend runs it. `model` is provider-SCOPED and is never translated across providers: a Gemini
# model id means nothing to the Claude CLI.
#
#   effort   Claude CLI (`--effort`)   Gemini (types.ThinkingConfig.thinking_level)
#   ------   ----------------------    -------------------------------------------
#   low      low                       LOW
#   medium   medium                    MEDIUM
#   high     high                      HIGH
#   xhigh    xhigh                     HIGH   (saturates — Gemini's ladder ends here)
#   max      max                       HIGH   (saturates)
#   (unset)  flag omitted              no thinking config sent
#
# The Gemini half is name-preserving on purpose: an event line reading effort=high must not mean
# MEDIUM. Its ladder has four rungs to the CLI's five, so the top two saturate rather than being
# renumbered downward, and Gemini's MINIMAL is unreachable because this ladder has no rung below
# `low` and inventing one would make `low` mean two different things across backends. The mapping
# itself lives in gemini.py, beside the call that uses it.
EFFORT_LEVELS = ("low", "medium", "high", "xhigh", "max")


def validate_effort(value, source):
    """Return `value` when it is a ladder level or None; raise ValueError otherwise. Never coerces.

    Validation exists because BOTH providers accept a bad level and keep going. The Claude CLI
    warns on stderr and runs at its own default (measured 2026-07-30, see CLAUDE_CLI_EFFORT below);
    Gemini would simply receive no thinking configuration. Either way the run completes, exits 0,
    and reports an effort nobody asked for — a silent degrade, not a crash.

    `source` names the thing being validated (an env var, or `effort=`) so the message points at
    the text the author actually wrote.
    """
    if value is None or value in EFFORT_LEVELS:
        return value
    raise ValueError(
        f"invalid {source} {value!r} — allowed: {' | '.join(EFFORT_LEVELS)} (or omit it to "
        f"inherit the provider default). Not coerced: a bad value would otherwise run at the "
        f"provider's default effort while the caller believes the request was honored."
    )

# Claude CLI fallback config. The fallback shells out to the local `claude`
# binary (Claude Code), which uses the user's existing Claude subscription —
# no separate API key, no separate billing. See src/rdg/claude.py for details.
CLAUDE_CLI_PATH = os.environ.get("CLAUDE_CLI_PATH", "claude")
CLAUDE_CLI_MODEL = os.environ.get("CLAUDE_CLI_MODEL", "sonnet")
CLAUDE_CLI_TIMEOUT_SECONDS = int(os.environ.get("CLAUDE_CLI_TIMEOUT_SECONDS", "600"))

# Claude CLI reasoning-effort level, passed through as `--effort <level>`.
#
# UNSET is the default and means the flag is OMITTED ENTIRELY, so the CLI's own
# default effort applies. That is the correct system-boundary pass-through: this
# engine does not have an opinion about effort, it only refuses to corrupt one.
#
# Validated HERE, at import, rather than at call time — because the CLI's own
# handling of a bad value is a SILENT DEGRADE. Measured 2026-07-30 against the
# installed CLI:
#
#     $ printf 'hi' | claude --print --model sonnet --effort xhgih
#     Warning: Unknown --effort value 'xhgih' — ignoring it and using the
#     default effort. Valid values: low, medium, high, xhigh, max.
#     <normal response>                                     # ← exit 0
#
# A typo therefore runs an entire pipeline at default effort while the caller
# believes the request was honored, and the only trace is a warning on a stderr
# stream that run_pipeline_bg redirects into a per-pipeline log. Refusing at
# import converts that into an immediate, unmissable failure.
#
# The empty string is INVALID, not "unset": `CLAUDE_CLI_EFFORT=` in a wrapper
# is a mistake worth surfacing, not a request for default behavior.
#
# Resolution + validation contract deliberately mirrors a consumer's
# established spawn wrapper (`CLAUDE_CLI_EFFORT` →
# `--effort`, never coerced, never forwarded) so the two dispatch mechanisms
# agree. Ladder per docs/operations/MODEL_ROUTING.md.
CLAUDE_CLI_EFFORT_LEVELS = EFFORT_LEVELS  # one ladder, engine-wide; name kept for readers
CLAUDE_CLI_EFFORT = validate_effort(os.environ.get("CLAUDE_CLI_EFFORT"), "CLAUDE_CLI_EFFORT")

# RDG primary backend. Default "gemini" preserves existing behavior (Gemini
# first, Claude as fallback on Gemini failure). Setting RDG_PRIMARY=claude
# skips Gemini entirely and routes every call to the Claude CLI. Use case:
# the Claude Code subscription is already paid for and you want to avoid
# Gemini's per-call billing surface for this run. Routing primary to Claude
# avoids the variable cost without losing the audit; the Gemini-first path
# remains the default so the change is opt-in / reversible.
RDG_PRIMARY = os.environ.get("RDG_PRIMARY", "gemini").lower()

# ---------------------------------------------------------------------------
# Gemini backend defaults for the standard parameters
# ---------------------------------------------------------------------------
#
# Same shape the Claude CLI block above already uses: a built-in default, env-overridable for a
# whole run, and overridable per step by `model=` / `effort=` in the .rdg line. The per-step form
# is the point — one pipeline can run its cheap gather steps on flash and its one judgement step
# on pro without a second process or a second engine config.
#
# The env vars are RDG_-prefixed: bare GEMINI_MODEL collides with Google's own gemini-cli, and a
# variable that silently repoints another tool's model is exactly the kind of action-at-a-distance
# this engine refuses. GEMINI_API_KEY keeps its name because that one IS the vendor's variable.
#
# RDG_GEMINI_EFFORT unset means NO thinking configuration is sent and the provider's own default
# applies, exactly as CLAUDE_CLI_EFFORT unset omits `--effort`. The empty string is INVALID rather
# than "unset" (`RDG_GEMINI_EFFORT=` in a wrapper is a mistake worth surfacing), and it is
# validated HERE at import so a typo cannot reach a run.
#
# THE one default model id — nothing else in the engine holds a second copy.
# History (kept for posterity — these were observed on this repo's key/SDK):
#   gemini-1.5-flash      -> 404 (auth not granted on this key)
#   gemini-2.0-flash-exp  -> 404 on v1beta in the old SDK version
GEMINI_MODEL_DEFAULT = "gemini-3-flash-preview"
GEMINI_MODEL = os.environ.get("RDG_GEMINI_MODEL", GEMINI_MODEL_DEFAULT)
GEMINI_EFFORT = validate_effort(os.environ.get("RDG_GEMINI_EFFORT"), "RDG_GEMINI_EFFORT")


def resolve_gemini_params(model, effort):
    """(model, effort) for a Gemini call: what the step asked for, else this run's defaults.

    Validation happens HERE, in the resolver, not only at the parser: this is the last point
    common to every path into a provider, so a level that reached it another way (a direct API
    caller, a future formula, an external module the parser passed through) cannot slip past into
    an argv or a thinking config.
    """
    return (model if model is not None else GEMINI_MODEL,
            validate_effort(effort, "effort=") if effort is not None else GEMINI_EFFORT)


def resolve_claude_params(model, effort):
    """(model, effort) for a Claude CLI call: what the step asked for, else this run's defaults.

    Validates for the same reason as resolve_gemini_params — and with sharper stakes: the CLI
    ACCEPTS an unknown `--effort`, warns on a stderr stream nobody reads on a green run, and
    completes at its default level.
    """
    return (model if model is not None else CLAUDE_CLI_MODEL,
            validate_effort(effort, "effort=") if effort is not None else CLAUDE_CLI_EFFORT)


def resolve_standard_params(model, effort):
    """(model, effort) as the PRIMARY backend for this run will resolve them.

    Used for the cache identity, which must describe the call that will actually be made. A
    Gemini→Claude FALLBACK resolves separately at its own call site, because that path uses the
    Claude backend's configured model rather than a Gemini id it could not honor.
    """
    if RDG_PRIMARY == "claude":
        return resolve_claude_params(model, effort)
    return resolve_gemini_params(model, effort)


def cache_identity(model, effort):
    """The part of a call's identity beyond its prompt, mixed INTO the md5 (never into the
    filename — cache entries stay `<32 hex>.json`, which is portable to filesystems that would
    reject `|` or a long name).

    EMPTY when the call is exactly the one this engine made before `model=`/`effort=` existed, so
    every response already on disk stays addressable (500+ entries in this repo's own
    .gemini_cache, and switch.py's byte-equality fast path re-derives the same md5 by hand).
    Anything else gets its own namespace: serving one model's cached answer as another model's
    answer is a phantom artifact — the exact failure class this engine refuses everywhere else,
    and the one that would make `model=` a claim rather than a fact.

    THE ASYMMETRY, STATED: "the default call" is resolved differently per backend. Under
    RDG_PRIMARY=claude the legacy pair is the CLI's CONFIGURED model/effort, because
    CLAUDE_CLI_MODEL/CLAUDE_CLI_EFFORT already selected the call before this feature existed;
    under Gemini it is the BUILT-IN model with no thinking config, because RDG_GEMINI_MODEL is new
    and a run that sets it is asking for a different call than the entries on disk describe. The
    rule is one sentence — the pair the engine would have used before standard parameters — and
    the asymmetry is in what that was, not in the rule.
    """
    resolved = resolve_standard_params(model, effort)
    legacy = ((CLAUDE_CLI_MODEL, CLAUDE_CLI_EFFORT) if RDG_PRIMARY == "claude"
              else (GEMINI_MODEL_DEFAULT, None))
    if resolved == legacy:
        return ""
    return f"|model={resolved[0]}|effort={resolved[1]}"