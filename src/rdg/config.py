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
# Resolution + validation contract deliberately mirrors rtb-manual's
# projects/rtb-cockpit/sidecar/spawn-claude.ts (`CLAUDE_CLI_EFFORT` →
# `--effort`, never coerced, never forwarded) so the two dispatch mechanisms
# agree. Ladder per docs/operations/MODEL_ROUTING.md.
CLAUDE_CLI_EFFORT_LEVELS = ("low", "medium", "high", "xhigh", "max")
CLAUDE_CLI_EFFORT = os.environ.get("CLAUDE_CLI_EFFORT")
if CLAUDE_CLI_EFFORT is not None and CLAUDE_CLI_EFFORT not in CLAUDE_CLI_EFFORT_LEVELS:
    raise ValueError(
        f"invalid CLAUDE_CLI_EFFORT {CLAUDE_CLI_EFFORT!r} — allowed: "
        f"{' | '.join(CLAUDE_CLI_EFFORT_LEVELS)} (or leave unset to inherit the "
        f"CLI default). Not coerced: the CLI would silently ignore a bad value "
        f"and run at default effort."
    )

# RDG primary backend. Default "gemini" preserves existing behavior (Gemini
# first, Claude as fallback on Gemini failure). Setting RDG_PRIMARY=claude
# skips Gemini entirely and routes every call to the Claude CLI. Use case:
# the Claude Code subscription is already paid for and you want to avoid
# Gemini's per-call billing surface for this run. Routing primary to Claude
# avoids the variable cost without losing the audit; the Gemini-first path
# remains the default so the change is opt-in / reversible.
RDG_PRIMARY = os.environ.get("RDG_PRIMARY", "gemini").lower()