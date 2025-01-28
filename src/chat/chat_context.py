import os
from ..rdg.file_ops import extract_output_files_and_commands
import logging

def create_context_from_files(rdg_file: str, output_files_and_commands: dict[str, str]) -> str:
    """
    Creates a context string from the output files specified in the RDG file.
    """
    context = ""
    rdg_dir = os.path.dirname(os.path.abspath(rdg_file))
    for output_file, command_data in output_files_and_commands.items():
        full_output_path = os.path.normpath(os.path.join(rdg_dir, output_file))
        try:
            if os.path.exists(full_output_path):
                with open(full_output_path, "r", encoding="utf-8") as f:
                    file_content = f.read()
                context += f"## {output_file}\n\n"
                context += "```\n"
                context += file_content
                context += "\n```\n\n"
            else:
                context += f"## {output_file}\n\n"
                context += "```\n"
                context += f"Warning: Could not find file {full_output_path}.\n"
                context += "\n```\n\n"
        except UnicodeDecodeError:
            print(f"Warning: Could not decode file content of {full_output_path}. Skipping content.")
            context += f"## {output_file}\n\n"
            context += "```\n"
            context += f"Warning: Could not decode content of {full_output_path} using utf-8 encoding.\n"
            context += "\n```\n\n"
        except Exception as e:
            print(f"Error reading file {full_output_path}: {e}")
    return context

def create_chat_context_from_rdg(rdg_file: str) -> str:
    """Creates a chat context from an RDG file."""
    file_dir = os.path.dirname(os.path.abspath(rdg_file))
    output_files_and_commands = extract_output_files_and_commands(rdg_file, file_dir)
    
    logging.info(f"[output_files_and_commands]: {output_files_and_commands}")
    context = create_context_from_files(rdg_file, output_files_and_commands)
    return context

def create_chat_context_from_files(files: list[str]) -> str:
    """Creates a chat context from a list of files."""
    context = ""
    for file_path in files:
        try:
            if os.path.exists(file_path):
                with open(file_path, "r", encoding="utf-8") as f:
                    file_content = f.read()
                context += f"## {file_path}\n\n"
                context += "```\n"
                context += file_content
                context += "\n```\n\n"
            else:
                context += f"## {file_path}\n\n"
                context += "```\n"
                context += f"Warning: Could not find file {file_path}.\n"
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

def create_chat_context_from_summaries(summaries: list[str]) -> str:
    """Creates a chat context from a list of summaries."""
    context = ""
    for summary in summaries:
        context += f"{summary}\n\n"
    return context