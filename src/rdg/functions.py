import os
import glob as glob_module
from pathlib import PurePath
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


def _parse_exclude_patterns(exclude_str: str) -> list[str]:
    """Split a comma-separated exclude string into stripped glob patterns.

    Mirrors how ``files=`` is comma-split + stripped. Empty entries (e.g. a
    trailing comma) are dropped so they cannot accidentally match every path.
    Returns an empty list when no exclude was supplied.
    """
    if not exclude_str:
        return []
    return [p.strip() for p in exclude_str.split(",") if p.strip()]


def _pattern_matches(pure: PurePath, pattern: str) -> bool:
    """Match ``pure`` against a single glob ``pattern`` with correct ``**``.

    ``fnmatch`` does NOT treat ``**`` as crossing ``/`` and Python's
    ``PurePath.match`` (pre-3.13 semantics, still the behavior of ``.match``)
    treats a leading ``**/`` as requiring AT LEAST ONE directory component — so
    ``**/*.spec.ts`` would miss a top-level ``foo.spec.ts``. We therefore prefer
    ``PurePath.full_match`` (Python 3.13+), whose ``**`` matches zero-or-more
    directory components — exactly what authors mean by ``**/*.spec.ts`` and
    ``**/__tests__/**``.

    On interpreters lacking ``full_match`` we degrade to ``.match`` plus a
    leading-``**/``-stripped retry, which recovers the top-level case rather
    than silently under-filtering.
    """
    full_match = getattr(pure, "full_match", None)
    if full_match is not None:
        return full_match(pattern)
    # Fallback for Python < 3.13: .match lacks zero-dir ** semantics.
    if pure.match(pattern):
        return True
    if pattern.startswith("**/"):
        return pure.match(pattern[len("**/"):])
    return False


def _is_excluded(rel_path: str, exclude_patterns: list[str]) -> bool:
    """True if ``rel_path`` matches ANY exclude glob pattern.

    Match is performed on the SAME path basis the caller uses for
    display/inclusion:
      - GLOBTOMARKDOWN passes the path relative to ``rdg_dir``.
      - FILESTOMARKDOWN passes the ``files=`` entry as given.

    Separators are normalised to ``/`` so behavior is deterministic regardless
    of host OS path style.
    """
    if not exclude_patterns:
        return False
    pure = PurePath(rel_path.replace(os.sep, "/"))
    for pattern in exclude_patterns:
        if _pattern_matches(pure, pattern.replace(os.sep, "/")):
            return True
    return False


def _reject_unknown_kwargs(kwargs: dict, allowed: set, fn_label: str) -> None:
    """Fail loud on any kwarg outside the per-function allowlist.

    Documented-intent kwargs that the function does not read are a silent
    contract violation (the original GLOBTOMARKDOWN/FILESTOMARKDOWN exclude bug:
    authors passed ``exclude=`` for 26 usages and it was dropped without a
    word). Surfacing unknown kwargs makes such typos/contract drift visible at
    parse time instead of producing phantom output.

    Allowlists verified zero-risk against every live ``apps/rtb-manual/.rdg``
    usage on 2026-06-08 (GLOBTOMARKDOWN: {pattern, exclude}; FILESTOMARKDOWN:
    {files, exclude} — no other kwarg appears in production).
    """
    unknown = sorted(k for k in kwargs if k not in allowed)
    if unknown:
        raise RdgParserError(
            f"Unknown parameter '{unknown[0]}' in {fn_label} "
            f"(allowed: {', '.join(sorted(allowed))})"
        )

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
      if "template" not in kwargs:
          raise RdgParserError("Template must be supplied when using the GEMINIPROMPT")
      template = kwargs.pop("template")

      input_data = {}
      for key, value in kwargs.items():
          # Pass file_dir to process input
          input_data[key] = process_input(value, os.path.dirname(rdg_file))

      rendered_template = render_template(template, input_data)

      logging.info(f"Rendered template:\n{rendered_template}")

      response_text = ollama_call(rendered_template)
      return response_text
  except Exception as e:
      raise RdgParserError(f"Error during LLM call: {e}")

def gemini_prompt(rdg_file:str, use_filesystem_cache=True, **kwargs) -> str:
    """Sends the file content to an LLM and returns the response using caching."""

    try:
        if "template" not in kwargs:
            raise RdgParserError("Template must be supplied when using the GEMINIPROMPT")
        template = kwargs.pop("template")

        input_data = {}
        for key, value in kwargs.items():
            # Pass file_dir to process input
            input_data[key] = process_input(value, os.path.dirname(rdg_file))

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
        if "template_file" not in kwargs:
            raise RdgParserError("Template file must be supplied when using the GEMINIPROMPTFILE")

        template_file = kwargs.pop("template_file")
        template_file = process_input(template_file, os.path.dirname(rdg_file))

        if os.path.exists(template_file):
            with open(template_file, 'r') as f:
                template = f.read()
        else:
            template = template_file

        input_data = {}
        for key, value in kwargs.items():
            # Pass file_dir to process input
            input_data[key] = process_input(value, os.path.dirname(rdg_file))

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
    _reject_unknown_kwargs(kwargs, {"files", "exclude"}, "FILESTOMARKDOWN")

    if "files" not in kwargs:
        raise RdgParserError("The parameter 'files' is required in FILESTOMARKDOWN")

    files_str = kwargs["files"]

    # Split the comma-separated string into a list of paths, stripping whitespace
    file_paths = [f.strip() for f in files_str.split(",")]

    # Optional exclude: comma-separated glob patterns. A file is dropped if it
    # matches ANY pattern, matched against the file_path entry as given (the
    # same path basis used for display below).
    exclude_patterns = _parse_exclude_patterns(kwargs.get("exclude", ""))
    file_paths = [
        fp for fp in file_paths if not _is_excluded(fp, exclude_patterns)
    ]

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
    _reject_unknown_kwargs(kwargs, {"pattern", "exclude"}, "GLOBTOMARKDOWN")

    if "pattern" not in kwargs:
        raise RdgParserError("The parameter 'pattern' is required in GLOBTOMARKDOWN")

    pattern = kwargs["pattern"]

    # Optional exclude: comma-separated glob patterns. A file is dropped if it
    # matches ANY pattern, matched against the rdg_dir-relative display path —
    # the same path basis used for inclusion/display below.
    exclude_patterns = _parse_exclude_patterns(kwargs.get("exclude", ""))

    # Resolve pattern relative to rdg file location
    rdg_dir = os.path.dirname(os.path.abspath(rdg_file))
    full_pattern = os.path.join(rdg_dir, pattern)

    # Expand glob pattern
    matches = glob_module.glob(full_pattern, recursive=True)

    # Filter to files only (glob can match directories)
    file_matches = [m for m in matches if os.path.isfile(m)]

    # Drop excluded files. Match exclude patterns against the rdg_dir-relative
    # path (identical to the display_path computed in the emit loop), so
    # `**/__tests__/**` and `**/*.spec.ts` filter as authors intend.
    file_matches = [
        m for m in file_matches
        if not _is_excluded(os.path.relpath(m, rdg_dir), exclude_patterns)
    ]

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
        if "template" not in kwargs:
            raise RdgParserError("Template must be supplied when using the CREATEGEMINIPROMPT")
        template = kwargs.pop("template")

        input_data = {}
        for key, value in kwargs.items():
            input_data[key] = process_input(value, os.path.dirname(rdg_file))

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


# ---------------------------------------------------------------------------
# RDG_FORMULA_PATH — load formulas from outside this package
# ---------------------------------------------------------------------------
#
# Lets a project add its own formulas without forking the engine. Set the env var to one or more
# directories (os.pathsep separated); every module in them exporting a FORMULAS dict is merged into
# FUNCTION_REGISTRY at import.
#
#     RDG_FORMULA_PATH=/path/to/my/formulas rdg my.rdg
#
# A formula module exports:
#
#     FORMULAS: Dict[str, Callable]      # name -> f(rdg_file: str, **kwargs) -> str
#
# matching what parser.py already calls — formula(rdg_file, **arguments) — whose return value is
# written to the step's destination.
#
# Loading is FAIL-LOUD. A path that does not exist, a module that will not import, or a module
# without a FORMULAS dict raises here rather than being skipped. A skipped module would leave its
# formulas undefined, and the parser would later report them as an unknown formula — sending the
# reader to their .rdg file to debug a typo that is not there.
def _load_external_formulas():
    import importlib.util
    import os
    import sys

    raw = os.environ.get("RDG_FORMULA_PATH", "")
    if not raw:
        return
    for directory in [d for d in raw.split(os.pathsep) if d]:
        if not os.path.isdir(directory):
            raise RuntimeError(
                f"RDG_FORMULA_PATH names '{directory}', which is not a directory"
            )
        for entry in sorted(os.listdir(directory)):
            if not entry.endswith(".py") or entry.startswith("_"):
                continue
            path = os.path.join(directory, entry)
            mod_name = "rdg_external_" + entry[:-3].replace("-", "_")
            spec = importlib.util.spec_from_file_location(mod_name, path)
            if spec is None or spec.loader is None:
                raise RuntimeError(f"could not load formula module {path}")
            module = importlib.util.module_from_spec(spec)
            sys.modules[mod_name] = module
            spec.loader.exec_module(module)
            formulas = getattr(module, "FORMULAS", None)
            if not isinstance(formulas, dict):
                raise RuntimeError(
                    f"{path} defines no FORMULAS dict — an external formula module must export "
                    "FORMULAS: Dict[str, Callable]"
                )
            for name, fn in formulas.items():
                FUNCTION_REGISTRY[name] = fn


_load_external_formulas()
