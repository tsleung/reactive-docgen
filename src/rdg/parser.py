import re
import os
import sys
from typing import Any
from .functions import FUNCTION_REGISTRY, RdgParserError

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
    argument_pairs = re.split(r',\s*(?=(?:[^\"]*\"[^\"]*\")*[^\"]*$)', arguments_str)

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
            arguments[arg_name] = arg_value
            

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
                    # Write error to output file so downstream consumers can see it
                    error_content = f"## ERROR\n\n{e}\n"
                    with open(output_path, 'w') as outfile:
                        outfile.write(error_content)
                except Exception as e:
                    print(f"An unexpected error occurred processing line '{line.strip()}': {e}", file=sys.stderr)
                    # Write error to output file so downstream consumers can see it
                    error_content = f"## ERROR\n\n{e}\n"
                    with open(output_path, 'w') as outfile:
                        outfile.write(error_content)
    except FileNotFoundError:
        print(f"Error: RDF file not found at '{rdg_file}'", file=sys.stderr)
    except Exception as e:
        print(f"An unexpected error occurred: {e}", file=sys.stderr)