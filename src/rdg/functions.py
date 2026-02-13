import os
import glob as glob_module
from .template import render_template
from .gemini import memoized_gemini_call, load_from_cache, save_to_cache, get_cache_key
from typing import Dict, Callable, Any
import logging
from ..llm.ollama import ollama_call

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

def ollama_prompt(rdg_file:str, use_filesystem_cache=True, **kwargs) -> str:
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

      response_text = ollama_call(rendered_template)
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
        rdg_file (str): The path to the rdg file (used for relative path resolution).
        directory_path (str): The path to the directory to process.
    """
    if "directory" not in kwargs:
        raise RdgParserError("The parameter 'directory' is required in DIRECTORYTOMARKDOWN")

    directory_path = kwargs["directory"]
    
    # Construct the absolute path to the directory relative to rdg_file
    rdg_dir = os.path.dirname(os.path.abspath(rdg_file))
    full_directory_path = os.path.normpath(os.path.join(rdg_dir, directory_path))

    try:
        output_content = ""
        if not os.path.exists(full_directory_path):
            raise FileNotFoundError(f"Directory not found: {directory_path}")

        for root, _, files in os.walk(full_directory_path):
            for file in files:
                file_path = os.path.join(root, file)
                # Make the displayed path relative to the initial directory_path provided by the user
                # This ensures consistency with how FILESTOMARKDOWN displays paths
                relative_to_full_dir = os.path.relpath(file_path, full_directory_path)
                display_path = os.path.join(directory_path, relative_to_full_dir)
                
                try:
                    with open(file_path, "r", encoding="utf-8") as f:
                        file_content = f.read()
                    output_content += f"## {display_path}\n\n"
                    output_content += "```\n"
                    output_content += file_content
                    output_content += "\n```\n\n"
                except UnicodeDecodeError:
                    print(f"Warning: Could not decode file content of {file_path}. Skipping content.")
                    output_content += f"## {display_path}\n\n"
                    output_content += "```\n"
                    output_content += f"Warning: Could not decode content of {file_path} using utf-8 encoding.\n"
                    output_content += "\n```\n\n"
                except Exception as e:
                    print(f"Error reading file {file_path}: {e}")
                    output_content += f"## {display_path}\n\n"
                    output_content += "```\n"
                    output_content += f"Error reading file {file_path}: {e}\n"
                    output_content += "\n```\n\n"

        return output_content
    except FileNotFoundError as e:
        raise RdgParserError(f"Error: {e}")
    except Exception as e:
        raise RdgParserError(f"An unexpected error occurred processing directory {directory_path}: {e}")

def create_markdown_from_files(rdg_file: str, **kwargs) -> str:
    """
    Gathers content from specified files and creates a markdown string with file paths
    and their content in code blocks.
    
    Args:
        rdg_file (str): The path to the rdg file (used for relative path resolution).
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
            output_content += f"## {file_path}\n\n"
            output_content += "```\n"
            output_content += f"Error reading file {file_path}: {e}\n"
            output_content += "\n```\n\n"
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

# Note: extract_output_files_and_commands is not defined in the provided context.
# Assuming it's defined elsewhere or is a placeholder for context purposes.
def create_single_markdown_file(rdg_file: str, output_file: str) -> None:
    """Creates a single markdown file from all RDG output files."""
    file_dir = os.path.dirname(os.path.abspath(rdg_file))
    # This function requires 'extract_output_files_and_commands' which is not in the provided snippet.
    # For a complete working example, this function would need to be defined.
    # output_files_and_commands = extract_output_files_and_commands(rdg_file, file_dir) 
    # context = create_context_from_files(rdg_file, output_files_and_commands)
    
    # Placeholder to avoid NameError if not defined
    output_files_and_commands = {} # Replace with actual parsing logic
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

def files_or_directories_to_markdown(rdg_file: str, **kwargs) -> str:
    """
    Gathers content from specified files and/or directories and creates a markdown string
    with file paths and their content in code blocks. Directories are expanded recursively.
    
    Args:
        rdg_file (str): The path to the rdg file.
        paths (str): A comma separated string of file and/or directory paths.
    """
    if "paths" not in kwargs:
        raise RdgParserError("The parameter 'paths' is required in FILESORDIRECTORIESTOMARKDOWN")

    paths_str = kwargs["paths"]
    
    # Split the comma-separated string into a list of paths, stripping whitespace
    items_to_process = [p.strip() for p in paths_str.split(",")]
    
    rdg_dir = os.path.dirname(os.path.abspath(rdg_file))
    output_content = ""

    for item_path in items_to_process:
        full_item_path = os.path.normpath(os.path.join(rdg_dir, item_path))
        
        if not os.path.exists(full_item_path):
            print(f"Warning: Path not found {item_path}. Skipping.")
            output_content += f"## {item_path}\n\n"
            output_content += "```\n"
            output_content += f"Warning: Path not found {item_path}.\n"
            output_content += "\n```\n\n"
            continue

        if os.path.isdir(full_item_path):
            # If it's a directory, use the existing DIRECTORYTOMARKDOWN logic
            try:
                # Pass the original item_path for consistency in display names
                output_content += create_markdown_from_directory(rdg_file, directory=item_path)
            except RdgParserError as e:
                print(f"Error processing directory {item_path}: {e}")
                output_content += f"## {item_path}\n\n"
                output_content += "```\n"
                output_content += f"Error processing directory {item_path}: {e}\n"
                output_content += "\n```\n\n"
        elif os.path.isfile(full_item_path):
            # If it's a file, use the existing FILESTOMARKDOWN logic for a single file
            try:
                # Pass the original item_path for consistency in display names
                output_content += create_markdown_from_files(rdg_file, files=item_path)
            except RdgParserError as e:
                print(f"Error processing file {item_path}: {e}")
                output_content += f"## {item_path}\n\n"
                output_content += "```\n"
                output_content += f"Error processing file {item_path}: {e}\n"
                output_content += "\n```\n\n"
        else:
            print(f"Warning: Path {item_path} is neither a file nor a directory. Skipping.")
            output_content += f"## {item_path}\n\n"
            output_content += "```\n"
            output_content += f"Warning: Path {item_path} is neither a file nor a directory.\n"
            output_content += "\n```\n\n"

    return output_content

def list_paths(rdg_file: str, **kwargs) -> str:
    """
    Lists all file and directory paths recursively within specified directories,
    or just the path itself if it's a file.
    
    Args:
        rdg_file (str): The path to the rdg file (used for relative path resolution).
        paths (str): A comma separated string of file and/or directory paths.
    """
    if "paths" not in kwargs:
        raise RdgParserError("The parameter 'paths' is required in LISTPATHS")

    paths_str = kwargs["paths"]
    
    # Split the comma-separated string into a list of paths, stripping whitespace
    items_to_process = [p.strip() for p in paths_str.split(",")]
    
    rdg_dir = os.path.dirname(os.path.abspath(rdg_file))
    listed_paths = []

    for item_path in items_to_process:
        full_item_path = os.path.normpath(os.path.join(rdg_dir, item_path))
        
        if not os.path.exists(full_item_path):
            print(f"Warning: Path not found: {item_path}")
            continue

        if os.path.isdir(full_item_path):
            # Recursively list all files and directories within this directory
            for root, dirs, files in os.walk(full_item_path):
                # Add directories first
                for d in dirs:
                    # Make the displayed path relative to the initial item_path provided by the user
                    relative_to_full_dir = os.path.relpath(os.path.join(root, d), full_item_path)
                    display_path = os.path.normpath(os.path.join(item_path, relative_to_full_dir))
                    listed_paths.append(display_path)
                # Then add files
                for f in files:
                    relative_to_full_dir = os.path.relpath(os.path.join(root, f), full_item_path)
                    display_path = os.path.normpath(os.path.join(item_path, relative_to_full_dir))
                    listed_paths.append(display_path)
        elif os.path.isfile(full_item_path):
            # If it's a file, just add its original path
            listed_paths.append(item_path)
        else:
            print(f"Warning: Path {item_path} is neither a file nor a directory.")
            
    return "\n".join(listed_paths)

def glob_to_markdown(rdg_file: str, **kwargs) -> str:
    """
    Gathers content from files matching a glob pattern and creates a markdown string
    with file paths and their content in code blocks.

    Args:
        rdg_file (str): The path to the rdg file (used for relative path resolution).
        pattern (str): A glob pattern (e.g., "src/**/*.py"). Supports recursive ** syntax.
    """
    if "pattern" not in kwargs:
        raise RdgParserError("The parameter 'pattern' is required in GLOBTOMARKDOWN")

    pattern = kwargs["pattern"]

    # Resolve pattern relative to rdg file location
    rdg_dir = os.path.dirname(os.path.abspath(rdg_file))
    full_pattern = os.path.join(rdg_dir, pattern)

    # Expand glob pattern
    matches = glob_module.glob(full_pattern, recursive=True)

    # Filter to files only (glob can match directories)
    file_matches = [m for m in matches if os.path.isfile(m)]

    # Sort for deterministic output
    file_matches.sort()

    if not file_matches:
        return f"No files matched pattern: {pattern}\n"

    output_content = ""
    for full_file_path in file_matches:
        # Display path relative to rdg_dir, preserving the pattern's directory structure
        display_path = os.path.relpath(full_file_path, rdg_dir)

        try:
            with open(full_file_path, "r", encoding="utf-8") as f:
                file_content = f.read()
            output_content += f"## {display_path}\n\n"
            output_content += "```\n"
            output_content += file_content
            output_content += "\n```\n\n"
        except UnicodeDecodeError:
            print(f"Warning: Could not decode file content of {display_path}. Skipping content.")
            output_content += f"## {display_path}\n\n"
            output_content += "```\n"
            output_content += f"Warning: Could not decode content of {display_path} using utf-8 encoding.\n"
            output_content += "\n```\n\n"
        except Exception as e:
            print(f"Error reading file {display_path}: {e}")
            output_content += f"## {display_path}\n\n"
            output_content += "```\n"
            output_content += f"Error reading file {display_path}: {e}\n"
            output_content += "\n```\n\n"

    return output_content

def create_gemini_prompt(rdg_file:str, **kwargs) -> str:
    """Returns the prompt that would be sent to Gemini, for debugging."""
    try:
        input_data = {}
        for key, value in kwargs.items():
            input_data[key] = process_input(value, os.path.dirname(rdg_file))
            
        if "template" in kwargs:
            template = kwargs.pop("template")
        else:
            raise RdgParserError("Template must be supplied when using the CREATEGEMINIPROMPT")
        rendered_template = render_template(template, input_data)

        logging.info(f"Rendered template for CREATEGEMINIPROMPT:\n{rendered_template}")
        return rendered_template
    except Exception as e:
        raise RdgParserError(f"Error creating Gemini prompt: {e}")


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
    "FILESORDIRECTORIESTOMARKDOWN": files_or_directories_to_markdown,
    "LISTPATHS": list_paths,
    "GLOBTOMARKDOWN": glob_to_markdown,
    "CREATEGEMINIPROMPT": create_gemini_prompt,
}