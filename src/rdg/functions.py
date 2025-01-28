import os
from .template import render_template
from .gemini import memoized_gemini_call, load_from_cache, save_to_cache, get_cache_key
from typing import Dict, Callable, Any
import logging


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
        file = process_input(file, os.path.dirname(rdg_file))
        
        if os.path.exists(file):
            with open(file, 'r') as f:
                content = f.read()
        else:
            content = file
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
    
    template_content = kwargs.pop("content")
    
    input_data = {}
    for key, value in kwargs.items():
        input_data[key] = process_input(value, os.path.dirname(rdg_file))
    
    file_content = render_template(template_content, input_data)
    
    return file_content

def gemini_prompt_template(rdg_file:str, use_filesystem_cache=True, **kwargs) -> str:
  
  if "template" not in kwargs:
      raise RdgParserError("Template must be supplied when using the GEMINIPROMPT")
  template = kwargs.pop("template")

  input_data = kwargs
  rendered_template = render_template(template, input_data)
  
  logging.info(f"Rendered template:\n{rendered_template}")

  try:
    cache_key = get_cache_key(rendered_template)
    cached_request, cached_response = load_from_cache(cache_key)

    if cached_response:
        # logging.info(f"Loaded from cache (key: {cache_key})")
        response_text = cached_response
    else:
        # logging.info(f"API Call (key: {cache_key})")
        response_text = memoized_gemini_call(rendered_template)
        if use_filesystem_cache:
            save_to_cache(cache_key, rendered_template, response_text)
    return response_text
  except Exception as e:
      raise RdgParserError(f"Error during LLM call: {e}")

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

def gemini_prompt_from_file(rdg_file:str, use_filesystem_cache=True, **kwargs) -> str:
    """Sends the file content to an LLM and returns the response using caching."""
    
    try:
        input_data = {}
        for key, value in kwargs.items():
            # Pass file_dir to process input
            input_data[key] = process_input(value, os.path.dirname(rdg_file))
            
        if "template_file" in kwargs:
            template_file = kwargs.pop("template_file")
            template_file = process_input(template_file, os.path.dirname(rdg_file))
            
            if os.path.exists(template_file):
                with open(template_file, 'r') as f:
                    template = f.read()
            else:
                template = template_file
        else:
            raise RdgParserError("Template file must be supplied when using the GEMINIPROMPTFILE")
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
    
    # Construct the absolute path to the directory relative to rdg_file
    rdg_dir = os.path.dirname(os.path.abspath(rdg_file))
    full_directory_path = os.path.normpath(os.path.join(rdg_dir, directory_path))

    try:
        output_content = ""
        for root, _, files in os.walk(full_directory_path):
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

def create_markdown_from_files(rdg_file: str, **kwargs) -> str:
    """
    Gathers content from specified files and creates a markdown string with file paths
    and their content in code blocks.
    
    Args:
        rdg_file (str): The path to the rdg file (not used)
        files (list): A comma separated string of file paths
    """
    if "files" not in kwargs:
        raise RdgParserError("The parameter 'files' is required in FILESTOMARKDOWN")

    files_str = kwargs["files"]
    
    # Split the comma-separated string into a list of paths, stripping whitespace
    file_paths = [f.strip() for f in files_str.split(",")]
    
    # Construct the absolute path to the directory relative to rdg_file
    rdg_dir = os.path.dirname(os.path.abspath(rdg_file))

    output_content = ""
    for file_path in file_paths:
        full_file_path = os.path.normpath(os.path.join(rdg_dir, file_path))
        try:
            with open(full_file_path, "r", encoding="utf-8") as f:
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

        except FileNotFoundError:
                print(f"Warning: File not found {file_path}. Skipping content.")
                output_content += f"## {file_path}\n\n"
                output_content += "```\n"
                output_content += f"Warning: Could not find file {file_path}.\n"
                output_content += "\n```\n\n"
        except Exception as e:
            print(f"Error reading file {file_path}: {e}")
    return output_content

def summarize_file(rdg_file: str, file: str, summary_type: str = "short") -> str:
    """Generates a summary of a file using the LLM."""
    try:
        file = process_input(file, os.path.dirname(rdg_file))
        if os.path.exists(file):
            with open(file, 'r') as f:
                content = f.read()
        else:
            content = file
        
        if summary_type == "short":
            prompt = f"Summarize the following text in a few sentences:\n\n{content}"
        elif summary_type == "long":
            prompt = f"Summarize the following text in detail:\n\n{content}"
        else:
            raise RdgParserError(f"Invalid summary type: {summary_type}")
        
        summary = gemini_prompt(rdg_file, template=prompt)
        return summary
    except Exception as e:
        raise RdgParserError(f"Error during summarization: {e}")

def create_single_markdown_file(rdg_file: str, output_file: str) -> None:
    """Creates a single markdown file from all RDG output files."""
    file_dir = os.path.dirname(os.path.abspath(rdg_file))
    output_files_and_commands = extract_output_files_and_commands(rdg_file, file_dir)
    context = create_context_from_files(rdg_file, output_files_and_commands)
    
    output_path = os.path.join(file_dir, output_file)
    with open(output_path, 'w') as outfile:
        outfile.write(context)

def rdg_to_file(rdg_file: str, output_file: str) -> str:
    """
    Converts all the output files of an RDG file into a single markdown file.
    """
    create_single_markdown_file(rdg_file, output_file)
    return f"Successfully created single markdown file: {output_file}"

def create_context_from_files(rdg_file: str, output_files_and_commands: dict) -> str:
        """
        Creates markdown context from generated files.
        """
        context = ""
        file_dir = os.path.dirname(os.path.abspath(rdg_file))
        for file_path, details in output_files_and_commands.items():
            full_file_path = os.path.join(file_dir, file_path)
            if os.path.exists(full_file_path):
                try:
                  with open(full_file_path, 'r') as f:
                      file_content = f.read()
                  context += f"## {file_path}\n\n"
                  context += "```\n"
                  context += file_content
                  context += "\n```\n\n"
                except UnicodeDecodeError:
                  print(f"Warning: Could not decode file content of {file_path}. Skipping content.")
                  context += f"## {file_path}\n\n"
                  context += "```\n"
                  context += f"Warning: Could not decode content of {file_path} using utf-8 encoding.\n"
                  context += "\n```\n\n"
                except Exception as e:
                    print(f"Error reading file {file_path}: {e}")
        return context

# FUNCTION_REGISTRY
FUNCTION_REGISTRY: Dict[str, Callable] = {
    "UPPERCASE": uppercase,
    "GEMINIPROMPT": gemini_prompt,
    "GEMINIPROMPTFILE": gemini_prompt_from_file,
    "DIRECTORYTOMARKDOWN": create_markdown_from_directory,
    "FILESTOMARKDOWN": create_markdown_from_files,
    "CREATEFILE": create_file,
    "SUMMARIZE": summarize_file,
    "RDGTOFILE": rdg_to_file,
}