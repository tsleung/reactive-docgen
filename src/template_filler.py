import os
import time
import subprocess
import logging
import argparse
import hashlib
import json
from functools import lru_cache
import google.generativeai as genai
from string import Template

LOG_FORMAT = '%(asctime)s - %(levelname)s - %(message)s'
logging.basicConfig(level=logging.INFO, format=LOG_FORMAT)

CACHE_DIR = ".gemini_cache"
os.makedirs(CACHE_DIR, exist_ok=True)

THROTTLE_SECONDS = 1
MAX_OUTPUT_TOKENS = 8000  # Set to the maximum allowed by Gemini


# --- Gemini API setup ---
api_key = os.environ.get("GEMINI_API_KEY")
if api_key:
    try:
        genai.configure(api_key=api_key)
        generation_config = {
          "temperature": 0.6,
          "top_p": 0.5,
          "top_k": 10,
          "max_output_tokens": 8192,
          "response_mime_type": "text/plain",
        }
        model = genai.GenerativeModel(
            # model_name="gemini-1.5-pro",
            # model_name="gemini-1.5-flash",
            model_name="gemini-2.0-flash-exp",
            generation_config=generation_config,
        )
        logging.info("Gemini API configured successfully.")
    except Exception as e:
        logging.error(f"Gemini API configuration failed: {e}")
        exit(1)
else:
    logging.error("GEMINI_API_KEY environment variable not set.")
    exit(1)

# --- Memoization ---
@lru_cache(maxsize=None)
def memoized_gemini_call(rendered_template):
    try:
        chat_session = model.start_chat(history=[])
        response = chat_session.send_message(rendered_template)
        # model.generate_content(
        #   rendered_template,
        #   generation_config=genai.types.GenerationConfig(
        #     # Only one candidate for now.
        #     candidate_count=1,
        #     # stop_sequences=["x"],
        #     max_output_tokens=8000,
        #     temperature=1.0,
        # ),
        # )
        
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


# --- Template processing ---
def render_template(template_str, input_data):
    try:
        template = Template(template_str)
        rendered = template.substitute(input_data)
        if not rendered.strip():
            raise ValueError("Rendered template is empty or contains only whitespace.")
        return rendered
    except KeyError as e:
        raise ValueError(f"Template placeholder not found: {e}")
    except Exception as e:
        raise RuntimeError(f"Template rendering failed: {e}")


def process_input(input_arg):
    current_directory = os.getcwd()
    file_path = os.path.join(current_directory, input_arg)
    logging.info(f"Checking for file: {file_path}")
    if os.path.exists(file_path):
        with open(file_path, 'r') as f:
            return f.read().strip()
    else:
        return input_arg


# --- Main functions ---
def fill_and_send_to_gemini(template_file, input_files, output_file, use_filesystem_cache=True):
    try:
        with open(template_file, 'r') as file:
            template_string = file.read()

        input_data = {}
        for key, value in input_files.items():
            input_data[key] = process_input(value)

        rendered_template = render_template(template_string, input_data)
        logging.info(f"Rendered template:\n{rendered_template}")

        cache_key = get_cache_key(rendered_template)
        cached_request, cached_response = load_from_cache(cache_key)

        if cached_response:
            logging.info(f"Loaded from cache (key: {cache_key})")
            response_text = cached_response
        else:
            logging.info(f"API Call (key: {cache_key})")
            response_text = memoized_gemini_call(rendered_template)
            if use_filesystem_cache:
                save_to_cache(cache_key, rendered_template, response_text)

        with open(output_file, 'w') as outfile:
            outfile.write(response_text)
        # logging.info(f"Response written to (file: {output_file})")
        print(f"Response written to '{output_file}'")

    except Exception as e:
        logging.exception(f"An unexpected error occurred: {e}")


def run_command(cmd):
    try:
        result = subprocess.run(cmd, shell=True, capture_output=True, text=True, check=True)
        logging.info(f"Command '{cmd}' successful:\n{result.stdout}")
    except subprocess.CalledProcessError as e:
        logging.error(f"Command '{cmd}' failed (return code {e.returncode}):\n{e.stderr}")
    except Exception as e:
        logging.exception(f"Unexpected error running command '{cmd}': {e}")


def watch_directory(path, command):
    last_modified_time = 0
    while True:
        try:
            modified_time = os.stat(path).st_mtime
            if time.time() - last_modified_time > THROTTLE_SECONDS and modified_time > last_modified_time:
                logging.info(f"Directory '{path}' modified. Running command.")
                run_command(command)
                last_modified_time = time.time()
            time.sleep(0.2)
        except KeyboardInterrupt:
            logging.info("Watcher stopped.")
            break
        except OSError as e:
            logging.error(f"Error accessing directory '{path}': {e}")
            break
        except Exception as e:
            logging.exception(f"Unexpected error: {e}")
            break

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description='Watch a directory and run a command.')
    parser.add_argument('path', help='Path to watch.')
    parser.add_argument('command', help='Command to run.')
    args = parser.parse_args()
    watch_directory(args.path, args.command)