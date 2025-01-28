import os
import logging
from .template import render_template

def process_input(input_arg, file_dir):
    file_path = os.path.join(file_dir, input_arg)
    logging.info(f"Checking for file: {file_path}")
    if os.path.exists(file_path):
        with open(file_path, 'r') as f:
            return f.read().strip()
    else:
        return input_arg

def extract_output_files_and_commands(rdg_file: str, file_dir: str) -> dict[str, str]:
    """
    Extracts output file paths and their associated commands from an RDG file.

    Args:
        rdg_file (str): Path to the RDG file.
        file_dir (str): The directory of the RDG file.

    Returns:
        dict[str, str]: A dictionary where keys are output file paths and values are the associated commands.
    """
    output_files_and_commands = {}
    try:
        with open(rdg_file, 'r') as f:
            for line in f:
                output_file, formula_name, arguments = parse_rdg_line(line, file_dir)
                if output_file:
                    output_files_and_commands[output_file] = {
                        "formula": formula_name,
                        "arguments": arguments
                    }
    except FileNotFoundError:
        print(f"Error: RDG file not found at '{rdg_file}'")
    except Exception as e:
        print(f"An unexpected error occurred: {e}")
    return output_files_and_commands