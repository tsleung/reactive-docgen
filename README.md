# reactive-docgen: Reactively Generate Documentation

`reactive-docgen` is a simple tool that allows you to generate documentation (or any kind of text files) by processing input files using a custom formula language, all driven by a simple text file called an rdg file (Reactive Document Generator). Think of it like a spreadsheet where cells contain formulas that can transform data - but for files instead of numbers.

This tool is powered by the Gemini LLM (Large Language Model), making it easy to perform tasks such as text summarization, translation, and other text manipulation.

## Getting Started

Here's a step-by-step guide on how to get `reactive-docgen` up and running on your machine:

### 1. Install Google Generative AI Library
This tool utilizes the `google-generativeai` library. You can install it using `pip`:

```bash
pip install google-generativeai python-dotenv
```
The `python-dotenv` library allows to use the API key using a `.env` file, which is more secure than exposing the API key in your terminal.

### 2. Create a Virtual Environment (Recommended)
A virtual environment is a way to create isolated Python environments. This avoids conflicts between different projects and keeps your system clean. To create and activate a virtual environment:

```bash
python3 -m venv .venv    # Creates a virtual environment called '.venv'
source .venv/bin/activate # Activates the virtual environment on macOS/Linux
# or
.venv\Scripts\activate   # Activates the virtual environment on Windows
```

### 3. Set Up Your Gemini API Key
1. You will need a Gemini API key. You can get one for free on the google AI platform website.
2. Once you have your key, create a `.env` file in the same directory as your `rdg.py` file.
3. Add the following line, replacing `your_api_key_here` with your actual API key:
   ```env
   GEMINI_API_KEY="your_api_key_here"
   ```

### 4. Understanding rdg Files

`reactive-docgen` uses a simple text file format called an rdg file. Each line in an rdg file represents a rule that describes how to process an input and create an output. Here's the basic format of each rule:

   ```
   <output_file>=<formula>(namedArgument1="value", namedArgument2="value")
   ```

   -   **`<output_file>`**:  The name of the file that will be created or overwritten with the results of the formula. The file will be created in the same directory as the rdg file, or within the directory specified in the output path. If a directory is specified in the output file path, it will be created automatically.
   -   **`<formula>`**: The name of the function to apply. Examples of formulas include `UPPERCASE` and `GEMINIPROMPT`.
   -   **`(...)`**: Inside the parentheses, we define **named arguments** for the formula. Each argument is defined as `argument_name="value"`.
   -  **named arguments**: arguments for the formula, these are key-value pairs that can take either a string or the path of a file. If a string is used, it must be encapsulated with quotes (either single or double quotes). File paths don't need any quotes.

   **Example `samples/sample.rdg` File:**

   ```
   samples/output.md=UPPERCASE(file="samples/input.md")
   samples/output2.md=GEMINIPROMPT(template="Summarize the following: $input", input="samples/input.md")
   samples/output3.md=GEMINIPROMPT(template="Translate to italian: $input", input="samples/input.md")
    samples/output5.md=GEMINIPROMPT(template="Translate to german: $input", input="samples/input.md")
   ```

   In the above example:

    - `UPPERCASE` converts the content of `samples/input.md` into uppercase, and outputs it to `samples/output.md`.
    - `GEMINIPROMPT` uses the Gemini LLM to summarize and translate the content of the `samples/input.md` file.

   **Available Formulas:**

    - `UPPERCASE`: Converts the content of a file to uppercase. It takes one keyword argument `file` (path to the input file).
    - `GEMINIPROMPT`: Uses the Gemini LLM to process text. Takes a keyword argument `template` (a string containing the template to use on the LLM, such as `Summarize the following: $input`, where `$input` is replaced by the content of the input file), and several file inputs (or strings) as keyword arguments.
  
### 5. Running the Script

To process an `rdg` file, use the following command, replacing `samples/sample.rdg` with the path to your `rdg` file:

   ```bash
   python src/rdg.py samples/sample.rdg
   ```
   
   If you are in the root directory, and have a `sample.rdg` file located inside the `samples` folder, then you can use the above command directly. This will automatically generate the `samples` directory, and the output files inside it. If you wish to run the script on another rdg file, simply change the path to your `rdg` file in the command above.

   This command will parse your `rdg` file, execute the formulas, and create output files.

### Example Workflow

Here's how you might use `reactive-docgen` in a real scenario:

1.  **Create a `docs/input.md` file:** and add some text:
    ```markdown
    # My Awesome Document
    This is the content of my documentation.
    I want to translate and uppercase this.
    ```
2. **Create a file called `docs/docgen.rdg`:** and add the following content:
    ```
    docs/output.md=UPPERCASE(file="docs/input.md")
    docs/summary.md=GEMINIPROMPT(template="Summarize the following text:\n$input", input="docs/input.md")
    docs/italian.md=GEMINIPROMPT(template="Translate the following text to italian:\n$input", input="docs/input.md")
    ```
3.  **Run the script**:
    ```bash
    python src/rdg.py docs/docgen.rdg
    ```
4.  After running the script, new output files will be created inside the `docs` folder. Each of the output files (`docs/output.md`, `docs/summary.md`, `docs/italian.md`) will contain the corresponding result of each formula.

### Notes on File Paths
- When defining the output file, the tool will create the directory of the output file if it doesn't exist. For example, if `output/folder/file.md` is passed as an output, and the folder `output/folder` doesn't exist, it will be created.
- All files are resolved relative to the folder where the `rdg` file is located.
- If a value in the `rdg` is passed with quotes (single or double), then it's treated as a string. Otherwise, the file path is resolved based on the rdg file location.

### Troubleshooting

*   **`ModuleNotFoundError: No module named 'dotenv'`:** Make sure that you have installed the required libraries: `pip install google-generativeai python-dotenv`.
*   **`GEMINI_API_KEY` not set:** Make sure to create the `.env` file and set the `GEMINI_API_KEY` variable.
*   **`RdfParserError: Template must be supplied when using the GEMINIPROMPT`**: Make sure that the template argument is included when calling the `GEMINIPROMPT` formula. Example: `GEMINIPROMPT(template="your template here", input="input.md")`
*   **Other issues:** Make sure the input files exist at the correct locations, and that you have internet connectivity if using the `GEMINIPROMPT` formula.

## Contributing

If you want to make this tool better, feel free to create a pull request with your suggestions and contributions!

## License

This project is licensed under the **GNU General Public License v3.0** (GPLv3). This license is chosen to ensure that the tool and any derivative works remain open-source and that its users are guaranteed certain freedoms.

