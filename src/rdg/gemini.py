import google.generativeai as genai
import logging
import hashlib
import json
import os
from functools import lru_cache
from .config import api_key, CACHE_DIR


if api_key:
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
            # model_name="gemini-1.5-flash",
            model_name="gemini-3-flash-preview",
            # model_name="gemini-2.5-pro",
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
    try:
        chat_session = model.start_chat(history=[])
        response = chat_session.send_message(rendered_template)
        
        return response.text
    except Exception as e:
        logging.error(f"Gemini API call failed: {e}")
        return ""


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