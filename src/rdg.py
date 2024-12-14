import re
import os
from string import Template
import logging
import argparse
from inspect import signature 
from functools import lru_cache
import hashlib
import json
import google.generativeai as genai

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

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
            model_name="gemini-1.5-flash",          
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
def memoized_gemini_call(prompt, **kwargs):  # Modified to accept kwargs
    try:
        chat_session = model.start_chat(history=[])
        response = chat_session.send_message(prompt)
        return response.text
    except Exception as e:
        logging.error(f"Gemini API call failed: {e}")
        return ""


def process_input(input_arg, context):
    if input_arg.startswith('"') and input_arg.endswith('"'):  # String literal
        return input_arg[1:-1]
    elif input_arg in context:
        return context[input_arg]
    elif os.path.exists(input_arg):
        with open(input_arg, 'r', encoding='utf-8') as f:
            return f.read().strip()
    return input_arg


def save_file(filepath, content):
    with open(filepath, "w", encoding='utf-8') as f:
        f.write(content)

def parse_rdg_file(filepath, context):
    with open(filepath, 'r', encoding='utf-8') as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith('#'):
                continue

            try:
                target, expression = line.split("=", 1)
                target = target.strip()
                expression = expression.strip()

                match = re.match(r"(.*?)\((.*)\)", expression)
                if match:  # Function/Formula call
                    func_name, args_str = match.groups()
                    func_name = func_name.strip()

                    if func_name in formula_registry:
                        func = formula_registry[func_name]
                        args = {}
                        positional_args = []

                        for arg in args_str.split(','):
                            if '=' in arg:
                                key, value = arg.split('=', 1)
                                args[key.strip()] = process_input(value.strip(), context)
                            elif arg.strip():
                                positional_args.append(process_input(arg.strip(), context))

                        # --- Dynamic Dispatch ---
                        try:
                          sig = signature(func)
                          bound_args = sig.bind(*positional_args, **args)  # changed this line
                          formula_result = func(*bound_args.args, **bound_args.kwargs, context=context)  # Pass context explicitly
                          if formula_result:
                              context[target] = formula_result
                              save_file(target, formula_result)

                        except TypeError as e:
                            logging.error(f"Incorrect arguments for formula/function '{func_name}' on line {line}: {e}")


                elif expression.startswith('"') and expression.endswith('"'): # Direct string assignment
                    context[target] = expression[1:-1]
                    save_file(target, context[target])
                else:  # Variable/Simple formula/template
                    context[target] = render_template(expression, context) # try rendering as a template string
                    if context[target]: # Check for successful render
                         save_file(target, context[target]) # save if render is successful


            except ValueError as e:
                logging.error(f"Invalid syntax on line: {line} - {e}")
            except Exception as e:
                logging.error(f"An unexpected error occurred on line {line}: {e}")

    
CACHE_DIR = ".gemini_cache"
os.makedirs(CACHE_DIR, exist_ok=True)

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


def uppercase(s, **kwargs):
    return s.upper()
 
 
def generate_content(template_string, context, use_cache=True):
    """Generates content using Gemini, utilizing caching."""
    rendered_template = render_template(template_string, context)
    if not rendered_template: # Handle rendering errors
        return None

    if use_cache:
        cache_key = get_cache_key(rendered_template)
        _, cached_response = load_from_cache(cache_key)

        if cached_response:
            logging.info(f"Loaded from cache (key: {cache_key})")
            return cached_response

    # if no cache, or cache miss.
    response_text = memoized_gemini_call(rendered_template)
    if use_cache:
        save_to_cache(cache_key, rendered_template, response_text)
    return response_text

def render_template(template_string, context):
    try:
        template = Template(template_string)
        return template.substitute(context)
    except KeyError as e:
        logging.error(f"Missing key in template context:{e} {template_string} {context}")
        return None
    except Exception as e:
        logging.error(f"Error rendering template: {e}")
        return None

def prompt_template_formula(template_string, target, **kwargs): # template_string instead of template_path
    context = kwargs.get('context', {})
    
    try:
      content = generate_content(template_string, context)  # Use the new function
      if content:  # Check if content was generated successfully
          context[target] = content
          return content
    except Exception as e:
      logging.info(f'prompt_template_formula kwargs: {kwargs}')
    return None
  
 
# Formula registry (includes promptTemplate)
formula_registry = {
    'uppercase': uppercase,
    'promptTemplate': lambda template_string, target, **kwargs: prompt_template_formula(template_string, target=target, **kwargs) # register promptTemplate
    # Add other formulas/functions here...
}


def main():
    parser = argparse.ArgumentParser(description="Reactive Document Generation")
    parser.add_argument("file", help="Path to the Reactive-DocGen file (.rdg)")
    args = parser.parse_args()

    context = {}
    parse_rdg_file(args.file, context)


    # try:
        # input("Press Enter to exit...\n")  # For now, since no background threads/processes
    # except KeyboardInterrupt:
        # print("Exiting...")


if __name__ == "__main__":
    main()