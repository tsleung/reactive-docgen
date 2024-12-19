import os
import argparse

def create_markdown_from_directory(directory_path, output_file="output.md"):
    """
    Recursively gathers files from a directory, creates a markdown file with file paths
    and contents in code blocks.

    Args:
        directory_path (str): The path to the directory to process.
        output_file (str, optional): The name of the output markdown file. Defaults to "output.md".
    """
    try:
      with open(output_file, "w", encoding="utf-8") as md_file:
        for root, _, files in os.walk(directory_path):
            for file in files:
                file_path = os.path.join(root, file)
                try:
                  with open(file_path, "r", encoding="utf-8") as f:
                      file_content = f.read()
                  md_file.write(f"## {file_path}\n\n")
                  md_file.write("```\n")
                  md_file.write(file_content)
                  md_file.write("\n```\n\n")
                except UnicodeDecodeError:
                  print(f"Warning: Could not decode file content of {file_path}. Skipping content.")
                  md_file.write(f"## {file_path}\n\n")
                  md_file.write("```\n")
                  md_file.write(f"Warning: Could not decode content of {file_path} using utf-8 encoding.\n")
                  md_file.write("\n```\n\n")

                except Exception as e:
                  print(f"Error reading file {file_path}: {e}")
    except FileNotFoundError:
        print(f"Error: Directory not found: {directory_path}")
    except Exception as e:
        print(f"An unexpected error occurred: {e}")
        

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Generate a markdown file from a directory's contents.")
    parser.add_argument("directory", type=str, help="The directory to process.")
    parser.add_argument("-o", "--output", type=str, default="output.md", help="The output markdown file name (default: output.md)")

    args = parser.parse_args()
    
    create_markdown_from_directory(args.directory, args.output)
    print(f"Markdown file '{args.output}' created successfully.")