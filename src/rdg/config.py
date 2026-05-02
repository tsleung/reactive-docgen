import os
import logging
from dotenv import load_dotenv

load_dotenv()

LOG_FORMAT = '%(asctime)s - %(levelname)s - %(message)s'
logging.basicConfig(level=logging.INFO, format=LOG_FORMAT)

CACHE_DIR = ".gemini_cache"
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