import os
import logging
from dotenv import load_dotenv

load_dotenv()

LOG_FORMAT = '%(asctime)s - %(levelname)s - %(message)s'
logging.basicConfig(level=logging.INFO, format=LOG_FORMAT)

CACHE_DIR = ".gemini_cache"
os.makedirs(CACHE_DIR, exist_ok=True)

THROTTLE_SECONDS = 1
MAX_OUTPUT_TOKENS = 8000  # Set to the maximum allowed by Gemini

api_key = os.environ.get("GEMINI_API_KEY")
anthropic_api_key = os.environ.get("ANTHROPIC_API_KEY")
# Claude model used as fallback when Gemini fails (quota, billing, 429, etc.)
# claude-sonnet-4-5 has a 200K context window — large enough for full pure-layer audits.
CLAUDE_FALLBACK_MODEL = os.environ.get("CLAUDE_FALLBACK_MODEL", "claude-sonnet-4-5")