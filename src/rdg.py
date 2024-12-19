import re
import os
import sys
from typing import Dict, Callable, Any
from dotenv import load_dotenv
import hashlib
import json
from functools import lru_cache
import time
import logging
from string import Template
import google.generativeai as genai

load_dotenv()  # Load .env file if present

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


def process_input(input_arg, file_dir):
    file_path = os.path.join(file_dir, input_arg)
    logging.info(f"Checking for file: {file_path}")
    if os.path.exists(file_path):
        with open(file_path, 'r') as f:
            return f.read().strip()
    else:
        return input_arg


class RdfParserError(Exception):
    """Custom exception for RDF parsing errors."""
    pass

def uppercase(rdg_file:str, **kwargs) -> str:
  """Converts the content of a file to uppercase."""
  try:
    if "file" not in kwargs:
        raise RdfParserError("The file parameter is required in UPPERCASE")
    file = kwargs["file"]
    with open(file, 'r') as f:
      content = f.read()
    return content.upper()
  except FileNotFoundError:
    raise RdfParserError(f"File not found: {file}")

def gemini_prompt(rdg_file:str, use_filesystem_cache=True, **kwargs) -> str:
    """Sends the file content to an LLM and returns the response using caching."""
    
    try:
        input_data = {}
        for key, value in kwargs.items():
            # Pass file_dir to process input
            input_data[key] = process_input(value, os.path.dirname(rdg_file))
            
        if "template" in kwargs:
            template = kwargs.pop("template")
        else:
          raise RdfParserError("Template must be supplied when using the GEMINIPROMPT")
        rendered_template = render_template(template, input_data)

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
        return response_text
    except Exception as e:
      raise RdfParserError(f"Error during LLM call: {e}")


# Function registry
FUNCTION_REGISTRY: Dict[str, Callable] = {
    "UPPERCASE": uppercase,
    "GEMINIPROMPT": gemini_prompt,
}

def parse_rdg_line(line: str, file_dir: str = ".") -> tuple[str, str, dict[str, Any]]:
    """Parses a single line of the rdg file."""
    line = line.strip()
    if not line or line.startswith("#"): # skip comments and empty lines
        return None, None, None
    
    match = re.match(r"([^=]+)=([^()]+)\((.*)\)", line) # Capture the full line
    if not match:
      raise RdfParserError(f"Invalid line format: {line}")

    output_file, formula_name, arguments_str = match.groups()
    output_file = output_file.strip()
    formula_name = formula_name.strip()
    
    if formula_name not in FUNCTION_REGISTRY:
        raise RdfParserError(f"Unknown formula: {formula_name}")

    arguments = {}
    for arg_pair in arguments_str.split(","):
        arg_pair = arg_pair.strip()
        if not arg_pair:
          continue
        arg_match = re.match(r"([^=]+)=(.*)", arg_pair)
        if not arg_match:
            raise RdfParserError(f"Invalid argument format: {arg_pair}")
        arg_name, arg_value = arg_match.groups()
        arg_name = arg_name.strip()
        arg_value = arg_value.strip()
        
        # check if string or file
        if arg_value.startswith('"') and arg_value.endswith('"') or arg_value.startswith("'") and arg_value.endswith("'"):
          # string, so we strip it.
          arguments[arg_name] = arg_value[1:-1]
        else:
          # file path so we expand it with file_dir
           arguments[arg_name] = os.path.join(file_dir, arg_value)

    return output_file, formula_name, arguments

def process_rdg_file(rdg_file: str, file_dir: str = ".") -> None:
    """Processes the given rdg file."""
    try:
        with open(rdg_file, 'r') as f:
            for line in f:
                output_file, formula_name, arguments = parse_rdg_line(line, file_dir)
                if not output_file:  # skip empty lines or comments
                    continue

                try:
                    formula = FUNCTION_REGISTRY[formula_name]
                    
                    # Create the output directory if it doesn't exist
                    output_path = os.path.join(file_dir, output_file)
                    output_dir = os.path.dirname(output_path)
                    if output_dir and not os.path.exists(output_dir):
                        os.makedirs(output_dir, exist_ok=True)

                    result = formula(rdg_file, **arguments)
                    with open(output_path, 'w') as outfile:
                        outfile.write(result)
                except RdfParserError as e:
                    print(f"Error processing line '{line.strip()}': {e}", file=sys.stderr)
                except Exception as e:
                    print(f"An unexpected error occurred processing line '{line.strip()}': {e}", file=sys.stderr)
    except FileNotFoundError:
        print(f"Error: RDF file not found at '{rdg_file}'", file=sys.stderr)
    except Exception as e:
        print(f"An unexpected error occurred: {e}", file=sys.stderr)

if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Usage: rdg.py <rdg_file>", file=sys.stderr)
        sys.exit(1)
    
    rdg_file = sys.argv[1]
    file_dir = os.path.dirname(os.path.abspath(rdg_file))  # get folder of rdg file
    process_rdg_file(rdg_file, file_dir)
    print("Rdf file parsed succesfully")