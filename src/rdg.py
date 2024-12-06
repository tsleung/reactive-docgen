import re
import os
from string import Template
import logging
import argparse

# from template_filler import fill_and_send_to_gemini  # Uncomment when using Gemini

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# Formula registry
formula_registry = {
    'uppercase': lambda s: s.upper()
    # Add more formulas here...
}

def process_input(input_arg, context):
    if input_arg in context:
        return context[input_arg]
    elif os.path.exists(input_arg):
        with open(input_arg, 'r', encoding='utf-8') as f:
            return f.read().strip()
    return input_arg


def render_template(template_string, context):
    try:
        template = Template(template_string)
        return template.substitute(context)
    except KeyError as e:
        logging.error(f"Missing key in template context: {e}")
        return None
    except Exception as e:
        logging.error(f"Error rendering template: {e}")
        return None

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
                    args = {}
                    for arg in args_str.split(','):
                        if '=' in arg:
                            key, value = arg.split('=', 1)
                            args[key.strip()] = process_input(value.strip(), context)
                        elif arg.strip():  # Handle positional arguments
                            args['_positional'] = process_input(arg.strip(), context)  # Store positional arg

                    if func_name == 'promptTemplate':
                        template_path = args.pop('template_path', args.pop('_positional', None)) # Get template_path from either named or positional arg.
                        if template_path is None: # Handle missing template.
                            logging.error(f"promptTemplate missing template_path argument in line: {line}") # Error message for missing template path.
                            continue

                        rendered_template = render_template(template_path, args)

                        if rendered_template: # check for successful render.
                            #fill_and_send_to_gemini(rendered_template, args, target) # Uncomment when using Gemini
                            save_file(target, rendered_template)
                            context[target] = rendered_template
                        

                    elif func_name in formula_registry:
                        formula_args = [process_input(a.strip(), context) for a in args_str.split(',')]
                        context[target] = formula_registry[func_name](*formula_args)
                        save_file(target, context[target])


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