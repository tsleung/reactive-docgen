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
          "temperature": 0.667,
          "top_p": 0.6,
          "top_k": 20,
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


class RdgParserError(Exception):
    """Custom exception for RDG parsing errors."""
    pass

def uppercase(rdg_file:str, **kwargs) -> str:
  """Converts the content of a file to uppercase."""
  try:
    if "file" not in kwargs:
        raise RdgParserError("The file parameter is required in UPPERCASE")
    file = kwargs["file"]
    with open(file, 'r') as f:
      content = f.read()
    return content.upper()
  except FileNotFoundError:
    raise RdgParserError(f"File not found: {file}")
  
def create_file(rdg_file:str, **kwargs) -> str:
    """
    Creates a file with a given string.
    
    Args:
      rdg_file (str): Path to the rdg file
      content (str): content of the file to be created
    """
   
    
    if "content" not in kwargs:
       raise RdgParserError("The parameter 'content' is required in CREATEFILE")
    
    
    file_content = kwargs["content"]
    
    return file_content

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
          raise RdgParserError("Template must be supplied when using the GEMINIPROMPT")
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
      raise RdgParserError(f"Error during LLM call: {e}")


def create_markdown_from_directory(rdg_file: str, **kwargs) -> str:
    """
    Recursively gathers files from a directory, creates a markdown file with file paths
    and contents in code blocks.

    Args:
        rdg_file (str): The path to the rdg file (not used)
        directory_path (str): The path to the directory to process.
        output_file (str, optional): The name of the output markdown file.
    """
    if "directory" not in kwargs:
         raise RdgParserError("The parameter 'directory' is required in DIRECTORYTOMARKDOWN")

    directory_path = kwargs["directory"]
    
    try:
        output_content = ""
        for root, _, files in os.walk(directory_path):
            for file in files:
                file_path = os.path.join(root, file)
                try:
                  with open(file_path, "r", encoding="utf-8") as f:
                      file_content = f.read()
                  output_content += f"## {file_path}\n\n"
                  output_content += "```\n"
                  output_content += file_content
                  output_content += "\n```\n\n"
                except UnicodeDecodeError:
                  print(f"Warning: Could not decode file content of {file_path}. Skipping content.")
                  output_content += f"## {file_path}\n\n"
                  output_content += "```\n"
                  output_content += f"Warning: Could not decode content of {file_path} using utf-8 encoding.\n"
                  output_content += "\n```\n\n"

                except Exception as e:
                  print(f"Error reading file {file_path}: {e}")
        return output_content
    except FileNotFoundError:
        raise RdgParserError(f"Error: Directory not found: {directory_path}")
    except Exception as e:
        raise RdgParserError(f"An unexpected error occurred: {e}")

# Function registry
FUNCTION_REGISTRY: Dict[str, Callable] = {
    "UPPERCASE": uppercase,
    "GEMINIPROMPT": gemini_prompt,
    "DIRECTORYTOMARKDOWN": create_markdown_from_directory,
    "CREATEFILE": create_file,
}

def parse_rdg_line(line: str, file_dir: str = ".") -> tuple[str, str, dict[str, Any]]:
    """Parses a single line of the rdg file."""
    line = line.strip()
    if not line or line.startswith("#"):
        return None, None, None

    match = re.match(r"([^=]+)=([^()]+)\((.*)\)", line)
    if not match:
        raise RdgParserError(f"Invalid line format: {line}")

    output_file, formula_name, arguments_str = match.groups()
    output_file = output_file.strip()
    formula_name = formula_name.strip()

    if formula_name not in FUNCTION_REGISTRY:
        raise RdgParserError(f"Unknown formula: {formula_name}")

    arguments = {}
    # Regex to split on commas outside of quotes
    argument_pairs = re.split(r',\s*(?=(?:[^"\']*["\'][^"\']*["\'])*[^"\']*$)', arguments_str)

    for arg_pair in argument_pairs:
        arg_pair = arg_pair.strip()
        if not arg_pair:
            continue
        arg_match = re.match(r"([^=]+)=(.*)", arg_pair)
        if not arg_match:
            raise RdgParserError(f"Invalid argument format: {arg_pair}")
        arg_name, arg_value = arg_match.groups()
        arg_name = arg_name.strip()
        arg_value = arg_value.strip()
        
        # check if string or file
        if (arg_value.startswith('"') and arg_value.endswith('"')) or (arg_value.startswith("'") and arg_value.endswith("'")):
          # string, so we strip it and handle escaped quotes
          arg_value = arg_value[1:-1]
          arg_value = arg_value.replace('\\"', '"').replace("\\'", "'")
          arguments[arg_name] = arg_value
        else:
          # file path so we expand it with file_dir and handle relative paths
           arguments[arg_name] = os.path.normpath(os.path.join(file_dir, arg_value))

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
                    
                    # Delete the output file if it exists
                    if os.path.exists(output_path):
                      os.remove(output_path)
                    
                    result = formula(rdg_file, **arguments)

                    with open(output_path, 'w') as outfile:
                        outfile.write(result)
                except RdgParserError as e:
                   
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
    print("Rdg file parsed succesfully")