
# reactive-docgen: Reactively Generate Docs

`reactive-docgen` is a tool that generates text files by processing input files using a custom formula language defined in an `rdg` file.  It's like a spreadsheet for files, where formulas transform data to create documents, stories, or simulate workflows.

This tool uses Large Language Models (LLMs) like Gemini and Ollama, enabling text generation, translation, and manipulation.  Extend it with custom formulas for specific use cases. `reactive-docgen` chains text changes, allowing the output of one formula to feed into another, creating reactive behavior. It focuses on **one-shot prompting** to LLMs, making output management straightforward.

## Getting Started

*   **Detailed Setup and Usage Guide**: For a thorough introduction, or if you're new to Python, see our [Detailed Setup and Usage Guide](detailed-setup.md).
*   **Sample Output:** See the [sample output directory](samples/).

### 1. Prerequisites

*   **Python 3.7+:**  Make sure you have Python 3.7 or later installed.
*   **pip:** Python's package installer.
*   **Git:** For cloning the repository.

### 2. Clone the Repository

```bash
git clone https://github.com/tsleung/reactive-docgen
cd reactive-docgen
```

### 3. Create a Virtual Environment (Recommended)

```bash
python3 -m venv .venv
source .venv/bin/activate  # macOS/Linux
# .venv\Scripts\activate  # Windows
```

### 4. Install Dependencies

```bash
pip install -r requirements.txt
```

### 5. Configure Your LLM API Key

#### Gemini API Key

1.  Get a Gemini API key for free from the [Google AI platform website](https://ai.google.dev/).
2.  Create a `.env` file in the root directory and add your API key:

    ```env
    GEMINI_API_KEY="your_api_key_here"
    ```

#### Ollama (Optional)

Ollama is a free, open-source, locally-run LLM. To use Ollama, you must first install it from [https://ollama.com/](https://ollama.com/). You will also need to pull a model, such as `llama2`.

```bash
ollama pull llama2
```

No API key is required for Ollama.

### 6. Understanding rdg Files

`rdg` files define the rules for processing input and creating output. Each line represents a rule:

```
<output_file>=<formula>(namedArgument1="value", namedArgument2="value")
```

-   **`<output_file>`**: The name of the file to create or overwrite.  The file will be created in the same directory as the `rdg` file, or within the directory specified in the output path. If a directory is specified in the output file path, it will be created automatically.
-   **`<formula>`**: The function to apply (e.g., `UPPERCASE`, `GEMINIPROMPT`, `CREATEFILE`, `DIRECTORYTOMARKDOWN`, `OLLAMAPROMPT`).
-   **`(...)`**: Named arguments for the formula, defined as `argument_name="value"`.
-   **named arguments**: arguments for the formula, these are key-value pairs that can take either a string or the path of a file. If a string is used, it must be encapsulated with quotes (either single or double quotes). File paths don't need any quotes.

**Example `sample.rdg` File:**

```
samples/hello.md=CREATEFILE(content="Ooo, Hello world?!")
samples/notes.md=UPPERCASE(file="samples/hello.md")
samples/workspace/draft.md=GEMINIPROMPT(template="You are an author. Create a story about the following: $input", input="samples/notes.md")
samples/workspace/feedback.md=GEMINIPROMPT(template="You are an editor. Provide feedback for the following story: $input", input="samples/workspace/draft.md")
samples/workspace/revision.md=GEMINIPROMPT(template="You are an author. Apply the provided feedback to your original draft, include comments: \n$feedback \n$story", feedback="samples/workspace/feedback.md", story="samples/workspace/draft.md")
samples/final.md=GEMINIPROMPT(template="You a publisher. Create the final version of the following story to copy and paste to print. Do not include any comments. This is the story: $story", story="samples/workspace/revision.md")
samples/pitch.md=GEMINIPROMPT(template="You're a story marketer. Create a short pitch about what this story is about: $input", input="samples/final.md")
samples/workspace/draft-italian.md=GEMINIPROMPT(template="You are a translator. Translate to italian. Add comments where the translation is difficult or the original meaning has been changed. Here is the text: $input", input="samples/final.md")
samples/story-italian.md=GEMINIPROMPT(template="Extract only the translated text. Do not include comments. This is the text: $input", input="samples/workspace/draft-italian.md")
samples/templates/pirate-reader.md=CREATEFILE(content="Read the story with a pirate accent. Do not include comments. This is the story: $input")
samples/story-pirate.md=GEMINIPROMPTFILE(template_file="samples/templates/pirate-reader.md", input="samples/final.md")
samples/all-notes.md=DIRECTORYTOMARKDOWN(directory="samples/workspace")
samples/single-file.md=RDGTOFILE(output_file="all_rdg_output.md")
```

**Available Formulas:**

*   `UPPERCASE`: Converts the content of a file to uppercase.  Takes `file` (path to the input file).
*   `GEMINIPROMPT`: Uses the Gemini LLM to process text. Takes `template` (a string containing the template to use on the LLM, such as `Summarize the following: $input`, where `$input` is replaced by the content of the input file), and several file inputs (or strings) as keyword arguments.
*   `GEMINIPROMPTFILE`: Same as `GEMINIPROMPT`, but takes the template from the specified template file path using the `template_file` argument.
*   `OLLAMAPROMPT`: Uses the Ollama LLM to process text.  Takes a `template` argument similar to `GEMINIPROMPT`.
*   `CREATEFILE`: Creates a file with the given content. Takes a `content` argument with the string that will be written in the output file.
*   `DIRECTORYTOMARKDOWN`: Takes a `directory` path as an argument and outputs the paths and content of all files (recursively) inside that directory in markdown format. Skips binary files and outputs an error message instead.
*   `FILESTOMARKDOWN`: Takes a `files` argument, which is a comma-separated list of file paths. Outputs the paths and content of the specified files in markdown format.
*   `SUMMARIZE`: Generates a summary of a file using the LLM. Takes a `file` argument (path to the input file) and an optional `summary_type` argument (either "short" or "long").
*   `RDGTOFILE`: Converts all the output files of an RDG file into a single markdown file. Takes an `output_file` argument specifying the name of the output markdown file.

### 7. Running the Script

To process an `rdg` file, use the following command, replacing `sample.rdg` with the path to your `rdg` file:

```bash
python src/rdg/rdg_cli.py sample.rdg
```

This command will parse your `rdg` file, execute the formulas, and create output files.

### 8. Script Watcher (Optional)

To automatically re-generate text whenever a file changes, use `script-watcher.py`.

1.  **Create a Shell Script (`sample.rdg.sh`)**:

    ```bash
    #!/bin/bash
    python src/rdg/rdg_cli.py sample.rdg
    ```

    Make the script executable:

    ```bash
    chmod +x sample.rdg.sh
    ```

2.  **Run the Script Watcher:**

    ```bash
    python src/script-watcher.py . ./sample.rdg.sh
    ```

    This watches the current directory (`.`) and runs `./sample.rdg.sh` when files change.

    An alternative .sh file
    ```
    #!/bin/bash
    python -m src.rdg.rdg_cli "$(dirname "$0")/.default.rdg"
    ```

### 9. Chatting with your RDG files

To chat with your RDG files, use the `chat_cli.py` script.

```bash
python src/chat/chat_cli.py sample.rdg
```

You can optionally specify a session ID to load chat history from a previous session.

```bash
python src/chat/chat_cli.py sample.rdg --session my_session
```

### Example Workflow

1.  **Create a `docs/docgen.rdg` file:**

    ```
    docs/input.md=CREATEFILE(content="# My Awesome Text\nThis is some content.\nI want to transform it.")
    docs/output.md=UPPERCASE(file="docs/input.md")
    docs/summary.md=GEMINIPROMPT(template="Summarize the following text:\n$input", input="docs/input.md")
    docs/italian.md=GEMINIPROMPT(template="Translate the following text to italian:\n$input", input="docs/input.md")
    docs/all_texts.md=DIRECTORYTOMARKDOWN(directory="docs")
    ```

2.  **Run the script**:

    ```bash
    python src/rdg/rdg_cli.py docs/docgen.rdg
    ```

### Notes on File Paths

*   The tool creates the output file's directory if it doesn't exist.
*   File paths are relative to the `rdg` file's location.
*   Values in quotes (single or double) are treated as strings; otherwise, they are file paths.

### Troubleshooting

*   **`ModuleNotFoundError`:** Install missing dependencies using `pip install -r requirements.txt`.
*   **`GEMINI_API_KEY` not set:** Create a `.env` file and set the `GEMINI_API_KEY` variable.
*   **`RdgParserError: Template must be supplied when using the GEMINIPROMPT`**: Include the `template` argument when calling `GEMINIPROMPT`.
*   **Permissions Issue:** Use `chmod +x <script_name>.sh` to grant execute permissions to shell scripts.

### Gemini Model

The tool is currently configured to use the `gemini-2.0-flash-exp` model. This can be changed in `src/rdg/gemini.py`.

## License

This project is licensed under the **GNU General Public License v3.0** (GPLv3).
