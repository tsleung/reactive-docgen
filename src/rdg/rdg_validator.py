

import re
import os

def parse_rdg_file(file_path):
    """
    Parses an .rdg file to extract output files and their dependencies.
    Returns a tuple:
    - defined_files (set): A set of all files defined as outputs.
    - used_files (set): A set of all files used as inputs.
    - dependency_graph (dict): A dictionary mapping output files to their input dependencies.
    """
    defined_files = set()
    used_files = set()
    dependency_graph = {}

    with open(file_path, 'r') as f:
        for line_num, line in enumerate(f, 1):
            line = line.strip()
            if not line or line.startswith('#'):
                continue

            match = re.match(r'([^=]+)=(.*)', line)
            if not match:
                print(f"Warning: Skipping malformed line {line_num}: {line}")
                continue

            output_file = match.group(1).strip()
            function_call = match.group(2).strip()

            defined_files.add(output_file)
            dependency_graph[output_file] = []

            # Regex to find file paths in function arguments
            # Looks for patterns like file="path/to/file.md", input="path/to/file.md", etc.
            # It also handles cases where the file path might be the entire argument value
            # e.g., GEMINIPROMPT(template="...", input="samples/final.md")
            # or DIRECTORYTOMARKDOWN(directory="samples/workspace")
            file_path_matches = re.findall(r'(?:file|input|feedback|story|directory|template_file)="([^"]+)"', function_call)
            
            # Also check for direct file paths as arguments without a key (less common but possible)
            # This is a more general regex that might catch non-file strings, so we'll filter later
            direct_arg_matches = re.findall(r'\b(\w+/\S+\.\w+)\b', function_call) # Basic check for path-like strings

            all_potential_inputs = set(file_path_matches)
            
            # Add direct_arg_matches, but filter out common non-file words if necessary
            for arg in direct_arg_matches:
                # Simple heuristic: if it looks like a path (contains / or .) and not a common keyword
                if '/' in arg or '.' in arg and not re.match(r'^(true|false|null|undefined)$', arg, re.IGNORECASE):
                    all_potential_inputs.add(arg)

            for input_file in all_potential_inputs:
                used_files.add(input_file)
                dependency_graph[output_file].append(input_file)
    
    return defined_files, used_files, dependency_graph

def validate_rdg_file(rdg_file_path):
    """
    Validates an .rdg file, identifies undefined inputs, and prints the dependency graph.
    """
    defined_files, used_files, dependency_graph = parse_rdg_file(rdg_file_path)

    print(f"--- Dependency Graph for {rdg_file_path} ---")
    for output, inputs in dependency_graph.items():
        if inputs:
            print(f"  {output} depends on:")
            for input_file in inputs:
                print(f"    - {input_file}")
        else:
            print(f"  {output} has no explicit file dependencies.")
    print("-------------------------------------------\n")

    undefined_inputs = used_files - defined_files

    internal_undefined_inputs = set()
    external_dependencies = set()
    base_dir = os.path.abspath(os.path.dirname(rdg_file_path))

    for undefined_input in sorted(list(undefined_inputs)):
        resolved_path = os.path.abspath(os.path.join(base_dir, undefined_input))

        # Check if the resolved path is within the base_dir or its subdirectories
        if resolved_path.startswith(base_dir + os.sep) or resolved_path == base_dir:
            internal_undefined_inputs.add(undefined_input)
        else:
            external_dependencies.add(undefined_input)

    if internal_undefined_inputs:
        print("--- Undefined Internal Inputs (relative to .rdg file, need to be defined or exist) ---")
        for u_input in sorted(list(internal_undefined_inputs)):
            print(f"- {u_input}")
        print("----------------------------------------------------------------------------------\n")
    else:
        print("No undefined internal inputs found.\n")

    if external_dependencies:
        print("--- External Dependencies (paths outside .rdg file's directory) ---")
        for e_dep in sorted(list(external_dependencies)):
            print(f"- {e_dep}")
        print("------------------------------------------------------------------\n")
    else:
        print("No external dependencies found.\n")

    # Check existence of all undefined inputs on filesystem
    print("--- Checking existence of all undefined inputs on filesystem ---")
    for undefined_input in sorted(list(undefined_inputs)):
        abs_path = os.path.abspath(os.path.join(base_dir, undefined_input))
        if os.path.exists(abs_path):
            print(f"  '{undefined_input}' exists on filesystem at '{abs_path}'")
        else:
            print(f"  WARNING: '{undefined_input}' does NOT exist on filesystem at '{abs_path}'")
    print("----------------------------------------------------------\n")

if __name__ == "__main__":
    # Example usage:
    # To run this, you would execute: python rdg_validator.py reactive-docgen/sample.rdg
    import sys
    if len(sys.argv) < 2:
        print("Usage: python rdg_validator.py <path_to_rdg_file>")
        sys.exit(1)

    rdg_file = sys.argv[1]
    if not os.path.exists(rdg_file):
        print(f"Error: File not found at {rdg_file}")
        sys.exit(1)
    
    validate_rdg_file(rdg_file)

