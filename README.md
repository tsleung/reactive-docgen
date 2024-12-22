# reactive-docgen: Reactively Generate Docs

`reactive-docgen` is a simple tool that allows you to generate text files by processing input files using a custom formula language, all driven by a simple text file called an `rdg` file. Think of it like a spreadsheet where cells contain formulas that can transform data – but for files instead of numbers. With `reactive-docgen`, you can generate a wide range of creative outputs, including documents, stories, game ideas, or even simulate workflows by adopting different advisory personas such as an investor, designer, or software engineer.

This tool uses Gemini, an LLM (Large Language Model), enabling you to perform tasks like text generation, translation, and a variety of text manipulations with ease. You can also extend it with your custom formulas for specific use cases. The unique ability of `reactive-docgen` is its capability to chain changes of texts, allowing the output of one formula to feed into the input of another formula, which allows for novel types of reactive behavior that can't be achieved by traditional LLM pipelines. Importantly, `reactive-docgen` focuses on **one-shot prompting** to LLMs, meaning each prompt to the LLM is independent and does not rely on previous interactions. This makes it straightforward to manage and reason about the output.

## Getting Started

Here's a step-by-step guide on how to get `reactive-docgen` up and running on your machine:

*   **Detailed Setup and Usage Guide**: For a thorough introduction, or you're unfamiliar with Python, see our [Detailed Setup and Usage Guide](detailed-setup.md).

### 1. Install Google Generative AI Library

This tool utilizes the `google-generativeai` library. You can install it using `pip`:

```bash
pip install google-generativeai python-dotenv
```

The `python-dotenv` library allows you to use the API key using a `.env` file, which is more secure than exposing the API key in your terminal.

### 2. Create a Virtual Environment (Recommended)

A virtual environment is a way to create isolated Python environments. This avoids conflicts between different projects and keeps your system clean. To create and activate a virtual environment:

```bash
python3 -m venv .venv    # Creates a virtual environment called '.venv'
source .venv/bin/activate # Activates the virtual environment on macOS/Linux
# or
.venv\Scripts\activate   # Activates the virtual environment on Windows
```

### 3. Set Up Your Gemini API Key

1.  You will need a Gemini API key. You can get one for free on the [Google AI platform website](https://ai.google.dev/).
2.  Once you have your key, create a `.env` file in the same directory as your `rdg.py` file.
3.  Add the following line, replacing `your_api_key_here` with your actual API key:

    ```env
    GEMINI_API_KEY="your_api_key_here"
    ```

### 4. Understanding rdg Files

`reactive-docgen` uses a simple text file format called an `rdg` file. Each line in an `rdg` file represents a rule that describes how to process an input and create an output. Here's the basic format of each rule:

```
<output_file>=<formula>(namedArgument1="value", namedArgument2="value")
```

-   **`<output_file>`**: The name of the file that will be created or overwritten with the results of the formula. The file will be created in the same directory as the `rdg` file, or within the directory specified in the output path. If a directory is specified in the output file path, it will be created automatically.
-   **`<formula>`**: The name of the function to apply. Examples of formulas include `UPPERCASE`, `GEMINIPROMPT`, `CREATEFILE`, and `DIRECTORYTOMARKDOWN`.
-   **`(...)`**: Inside the parentheses, we define **named arguments** for the formula. Each argument is defined as `argument_name="value"`.
-   **named arguments**: arguments for the formula, these are key-value pairs that can take either a string or the path of a file. If a string is used, it must be encapsulated with quotes (either single or double quotes). File paths don't need any quotes.

**Example `sample.rdg` File:**

```
samples/hello.md=CREATEFILE(content="Hello world?!")
samples/output.md=UPPERCASE(file="samples/hello.md")
samples/output2.md=GEMINIPROMPT(template="Create a story about the following: $input", input="samples/output.md")
samples/output3.md=GEMINIPROMPT(template="Translate to italian: $input", input="samples/output2.md")
samples/output4.md=GEMINIPROMPT(template="Translate to german: $input", input="samples/output2.md")
samples/template.md=CREATEFILE(content="Write a story with a pirate accent $input")
samples/output5.md=GEMINIPROMPTFILE(template_file="samples/template.md", input="samples/output.md")
samples/directory.md=DIRECTORYTOMARKDOWN(directory="samples")
```

In the above example:

*   `CREATEFILE` creates a file named `samples/hello.md` with the content `Hello world?!`.
*   `UPPERCASE` converts the content of `samples/hello.md` into uppercase, and outputs it to `samples/output.md`.
*   `GEMINIPROMPT` uses the Gemini LLM to create a story from the content of the `samples/output.md` file, then translates it to Italian and German.
*  `GEMINIPROMPTFILE` loads a template file `samples/template.md`, and generates a file `samples/output5.md` based on that template with the content of `samples/output.md` as input.
*   `DIRECTORYTOMARKDOWN` takes all the files inside the `samples` directory, and creates a markdown file with their paths and contents inside a code block.

**Available Formulas:**

*   `UPPERCASE`: Converts the content of a file to uppercase. It takes one keyword argument `file` (path to the input file).
*   `GEMINIPROMPT`: Uses the Gemini LLM to process text. Takes a keyword argument `template` (a string containing the template to use on the LLM, such as `Summarize the following: $input`, where `$input` is replaced by the content of the input file), and several file inputs (or strings) as keyword arguments.
*   `GEMINIPROMPTFILE`: Same as GEMINIPROMPT, but takes the template from the specified template file path using the `template_file` argument.
*   `CREATEFILE`: Creates a file with the given content. Takes a `content` argument with the string that will be written in the output file.
*   `DIRECTORYTOMARKDOWN`: Takes a `directory` path as an argument, and outputs the paths and content of all files (recursively) inside that directory. Skips binary files, and outputs an error message instead.

### 5. Running the Script

To process an `rdg` file, use the following command, replacing `sample.rdg` with the path to your `rdg` file:

```bash
python src/rdg.py sample.rdg
```

If you are in the root directory, and have a `sample.rdg` file located inside the `samples` folder, then you can use the above command directly. This will automatically generate the `samples` directory, and the output files inside it. If you wish to run the script on another rdg file, simply change the path to your `rdg` file in the command above.

This command will parse your `rdg` file, execute the formulas, and create output files.

### 6. Script Watcher (Optional)

For scenarios where you want to automatically re-generate text whenever a file changes, you can use the `script-watcher.py`. This script watches a directory and executes a command (like running your `rdg.py` script) when changes are detected.

1.  **Create a Shell Script (`sample.rdg.sh`)**: This script will contain the command to run, such as running `rdg.py` with your rdg file. Create a `sample.rdg.sh` file with the following content (or whatever name you want for your script):

    ```bash
    #!/bin/bash
    python src/rdg.py sample.rdg
    ```

    **Important:** Make sure that this file has execute permissions. Run `chmod +x sample.rdg.sh` to give the script execute permissions. You can run this command directly on the terminal, or copy paste this into a terminal:

    ```bash
    chmod +x sample.rdg.sh
    ```

    Note that this also works with any other command. For instance, if you wish to just copy the files inside the directory `samples` to a folder called `samples-copy` whenever you modify something in the `samples` directory, then you can create a command as:

    ```bash
    cp -r samples samples-copy
    ```

    This is just an example, and any other command can be used.

2.  **Run the Script Watcher:** To use the script watcher, run:

    ```bash
    python src/script-watcher.py . ./sample.rdg.sh
    ```

    This command watches the current directory (`.`) and runs the `./sample.rdg.sh` command whenever any files inside the current directory (or any of its subdirectories) are changed.

    **Explanation of the command:**

    *   **`python src/script-watcher.py`**: This is the command that will execute the `script-watcher.py` file.
    *   **`.`**: This specifies the directory to watch for changes.
    *   **`./sample.rdg.sh`**: This is the shell command to execute when changes are detected.

**Note:**

*   The script watcher will re-run the command every time the files inside the watched directory have been modified.
*   Make sure the `.rdg` file used in the shell script exists.
*   Remember that if you specify the rdg file as `/path/to/your/rdg` then you must also specify the path where the file is located in your shell script.

### Example Workflow

Here's how you might use `reactive-docgen` in a real scenario:

1.  **Create a `docs/docgen.rdg` file:** and add the following content:

    ```
    docs/input.md=CREATEFILE(content="# My Awesome Text\nThis is some content.\nI want to transform it.")
    docs/output.md=UPPERCASE(file="docs/input.md")
    docs/summary.md=GEMINIPROMPT(template="Summarize the following text:\n$input", input="docs/input.md")
    docs/italian.md=GEMINIPROMPT(template="Translate the following text to italian:\n$input", input="docs/input.md")
    docs/all_texts.md=DIRECTORYTOMARKDOWN(directory="docs")
    ```

2.  **Run the script**:

    ```bash
    python src/rdg.py docs/docgen.rdg
    ```

3.  After running the script, new output files will be created inside the `docs` folder. Each of the output files (`docs/input.md`, `docs/output.md`, `docs/summary.md`, `docs/italian.md` and `docs/all_texts.md`) will contain the corresponding result of each formula.

### Notes on File Paths

*   When defining the output file, the tool will create the directory of the output file if it doesn't exist. For example, if `output/folder/file.md` is passed as an output, and the folder `output/folder` doesn't exist, it will be created.
*   All file paths are resolved relative to the folder where the `rdg` file is located.
*   If a value in the `rdg` is passed with quotes (single or double), then it's treated as a string. Otherwise, the file path is resolved based on the rdg file location.

### Troubleshooting

*   **`ModuleNotFoundError: No module named 'dotenv'`:** Make sure that you have installed the required libraries: `pip install google-generativeai python-dotenv`.
*   **`GEMINI_API_KEY` not set:** Make sure to create the `.env` file and set the `GEMINI_API_KEY` variable.
*   **`RdgParserError: Template must be supplied when using the GEMINIPROMPT`**: Make sure that the template argument is included when calling the `GEMINIPROMPT` formula. Example: `GEMINIPROMPT(template="your template here", input="input.md")`
*   **Other issues:** Make sure the input files exist at the correct locations, and that you have internet connectivity if using the `GEMINIPROMPT` formula. Check the console for any errors or warning messages.

### Permissions Issue for Scripts

The "permission denied" error means that the script `sample.rdg.sh` doesn't have execute permission. You need to make it executable using the `chmod` command:

```
chmod +x sample.rdg.sh
```

Here's how you can grant execute permission recursively:

```
chmod -R +x /path/to/your/directory
```

A more targeted and safer approach is to grant execute permission only to files ending in `.sh` (or whatever extension you use for your shell scripts):

```
find /path/to/your/directory -name "*.sh" -exec chmod +x {} \;
```

If you have scripts using different interpreters (e.g., Bash, Python, etc.), you can use `find` with more specific criteria:

```
find /path/to/your/directory \( -name "*.sh" -o -name "*.py" \) -exec chmod +x {} \;
```

## License

This project is licensed under the **GNU General Public License v3.0** (GPLv3). This license is chosen to ensure that the tool and any derivative works remain open-source and that its users are guaranteed certain freedoms.
