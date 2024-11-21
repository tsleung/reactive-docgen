import argparse
from template_filler import fill_and_send_to_gemini

def main():
    parser = argparse.ArgumentParser(description="Fill a template with inputs and send to Gemini.")
    parser.add_argument("template", help="Path to the template file.")
    parser.add_argument("output", help="Path to the output file.")
    parser.add_argument("inputs", nargs="+", help="Input data (filenames or strings).  Format: key=value")
    args = parser.parse_args()

    input_files = {}
    for input_pair in args.inputs:
        try:
            key, value = input_pair.split("=")
            input_files[key] = value
        except ValueError:
            print("Error: Invalid input format. Use key=value.")
            return

    fill_and_send_to_gemini(args.template, input_files, args.output)

if __name__ == "__main__":
    main()