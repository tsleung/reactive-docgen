# Detailed Setup and Usage Guide for reactive-docgen

Welcome to `reactive-docgen`! This tool empowers you to generate text files by processing input files according to a set of instructions you define. It offers a straightforward way to automate text transformations and content generation.

## What is reactive-docgen?

`reactive-docgen` is designed to make text processing more efficient and automated. It uses a special type of file (an `rdg` file) to outline the steps needed to turn input files into output files. This can involve tasks like summarizing, translating, or generating new content based on existing files.

## Before You Begin

**Important Note:** To run `reactive-docgen`, you need to have Python and `pip` (Python package installer) installed on your computer. Python is a programming language, and `pip` is a tool that helps you install additional libraries (like `google-generativeai`) which the tool needs. This guide will include some basic instructions; however, if you are not using macOS and are having issues, you may need to search online for specific instructions on how to install Python for your operating system. You will also need a Google account with access to the Gemini AI model and a Gemini API key, which you can acquire for free.

## Step-by-Step Guide

### 0. Install Python, pip, and Git (Primarily for macOS)

*   **What are Python, pip, and Git?** Python is a programming language that `reactive-docgen` is written in, and `pip` is a tool used for downloading and installing necessary tools that extend the basic python functionality, these tools are called "packages" or "libraries". Git is a version control system that allows you to clone repositories from services such as GitHub.
*   **Check if you have Python:** Open your **Terminal** (found in Applications > Utilities on macOS) or Command Prompt (Windows) and type `python3 --version` (or `python --version` on some systems) then press Enter.
    *   If you get a version number (e.g., `Python 3.9.6`), you have Python installed.
    *   If you get an error, you likely don't have it installed, or it isn't in your PATH.
*   **Download Python:** If needed, go to the official [Python website](https://www.python.org/downloads/) and download the appropriate installer for your operating system.
*   **Run the Installer:** Execute the downloaded installer and follow the instructions, ensuring you select the "Add Python to PATH" or similar option during the installation process. This allows you to run Python commands from your terminal or command prompt.
*   **Check if you have pip:** Open your terminal or command prompt and type `pip3 --version` (or `pip --version`) then press Enter. If you get a version number, you have `pip` installed. `pip` is usually installed by default if you installed Python correctly.
    *   If you don't get a version number, please try re-installing Python and ensure you select the option to add to path.
*   **Check if you have Git:** Open your terminal or command prompt and type `git --version` then press Enter.
    *   If you get a version number (e.g., `git version 2.39.2`), you have Git installed.
    *   If you get an error, you likely don't have it installed.
*   **Download Git (if needed):** If you don't have Git installed, go to the official [Git website](https://git-scm.com/downloads) and download the appropriate installer for your operating system.
*   **Run the Git Installer:** Execute the downloaded Git installer and follow the instructions. You can usually accept the default settings.

### 1. Copy the `reactive-docgen` Code to Your Computer

This step involves downloading the files so you can use the tool. This process is known as "cloning".

*   **Cloning Options:** You have a few options for this step:

    *   **Using GitHub Desktop:**
        *   Navigate to the [reactive-docgen repository](https://github.com/your-repo-link).
        *   Click the green "Code" button and choose "Open with GitHub Desktop".
        *   If you don't have GitHub Desktop, you'll be prompted to install it. Follow the instructions to download it.
        *   After cloning, a copy of the code will be on your computer in the specified location.
    *   **Using Command Line (macOS):**
        *   Open your **Terminal** (found in Applications > Utilities).
        *   Use the following command, replacing `your-repo-link` with the actual link to the GitHub repository for `reactive-docgen`:

            ```bash
            git clone https://github.com/tsleung/reactive-docgen
            ```
        *   The `reactive-docgen` will now be downloaded to your computer in the directory where you executed the command.
        *   **For other operating systems**: Use the terminal application available in your OS.

### 2. (Optional) Create a Virtual Environment (macOS)

*   **What is a Virtual Environment?** A virtual environment is a way to create isolated Python environments. This helps avoid conflicts between different projects that may require different versions of the same packages, and is a recommended practice for any project that uses Python.
*   Using a virtual environment isolates your Python installations, and is recommended.
*   **Open your Terminal** (found in Applications > Utilities).
*   **Navigate to the `reactive-docgen` directory:** Use the `cd` command followed by the path to your `reactive-docgen` directory and press Enter.
*   **Type the following commands one by one:**

    ```bash
    python3 -m venv .venv # creates a virtual environment called .venv
    source .venv/bin/activate # activates the virtual environment
    ```
 *   **For other operating systems**: you may have to search for platform specific instructions for setting up a virtual environment.

### 3. Set Up Your Gemini API Key

To allow `reactive-docgen` to interact with the Gemini AI model, you'll need to set up a Gemini API key.

1.  Go to the [Google AI platform website](https://ai.google.dev/) and sign in with your Google account.
2.  Follow the instructions to get a Gemini API key. This is provided free of charge.
3.  **Create a `.env` file:**
    *   Open any text editor on your computer, such as TextEdit (macOS) or Visual Studio Code (recommended)
    *   Type the following line into the editor, replacing `your_api_key_here` with the Gemini API key you obtained:

        ```
        GEMINI_API_KEY="your_api_key_here"
        ```

        Be sure to include the double quotes around your API key.
    *   Save the file with the name `.env` in the same folder where you downloaded the `reactive-docgen` code.
        *   Ensure that the file is saved as "All Files" to avoid accidentally saving it as a `.txt` file.

### 4. Run the `sample.rdg` File

With the code and API key configured, you can now execute the `sample.rdg` file.

1.  **Open a Terminal Window (macOS):** Open your **Terminal** (found in Applications > Utilities).
      *    **For other operating systems**: Use the terminal application available in your OS.
2.  **Navigate to the `reactive-docgen` Directory:**

    *   Use the `cd` command in the terminal followed by a space and then the full path to your `reactive-docgen` folder, then press Enter.
        * If your `reactive-docgen` folder is on your desktop, then an example of what you'd write is `cd /Users/YourUserName/Desktop/reactive-docgen` on macOS (replace `YourUserName` with your actual username).
        * You can also type `cd` and then drag the folder containing `reactive-docgen` from your file explorer into the terminal, this will automatically fill in the directory path.

3.  **Execute the Script:**

    *   Enter the following command in your terminal and press Enter:

        ```bash
        python src/rdg.py samples/sample.rdg
        ```

        This will run the `reactive-docgen` program, processing the instructions in the `sample.rdg` file.

4.  **View Output Files:**

    *   After a brief moment, new files will appear in the `samples` folder within the `reactive-docgen` folder. These files are the results of processing your input using the Gemini AI model, based on the `sample.rdg` file. You may use a code editor such as Visual Studio Code (VS Code) to view your output.

## What to Expect

When you run `samples/sample.rdg`, it will generate several new files within the `samples` folder, including subfolders such as `samples/workspace`. These files are the results of processing your input using the Gemini AI model, based on the `sample.rdg` file.

Specifically, the following files will be generated:

-   `samples/hello.md`: A file containing the text "Ooo, Hello world?!".
-   `samples/notes.md`: A file containing the uppercase version of `samples/hello.md`.
-   `samples/workspace/draft.md`: A file containing a story based on the content of `samples/notes.md`.
-   `samples/workspace/feedback.md`: A file containing feedback for the story in `samples/workspace/draft.md`.
-   `samples/workspace/revision.md`: A file containing a revision of the story from `samples/workspace/draft.md`, incorporating the feedback from `samples/workspace/feedback.md`, including comments.
-   `samples/final.md`: A final version of the story from `samples/workspace/revision.md` without any comments.
-   `samples/pitch.md`: A short pitch about the story in `samples/final.md`.
-   `samples/workspace/draft-italian.md`: A file containing the Italian translation of the final story with comments about difficult translations.
-   `samples/story-italian.md`: A file containing only the translated text of the story in `samples/workspace/draft-italian.md`, without comments.
-   `samples/templates/pirate-reader.md`: A template file to read the story with a pirate accent, which is not shown to the user directly.
-   `samples/story-pirate.md`: A file containing the story read with a pirate accent, based on `samples/final.md` using the `samples/templates/pirate-reader.md` template.
-   `samples/all-notes.md`: A file containing all the files inside the directory `samples/workspace` in a markdown format.

You may use a code editor such as Visual Studio Code (VS Code) to view your output.

## Next Steps

You have now successfully run `reactive-docgen` for the first time!

*   **Explore `sample.rdg`**: Take a look at the `sample.rdg` file to understand the different operations being performed.
*   **Experiment**: Try modifying `sample.rdg` or creating your own `rdg` files with custom rules.
*   **Try New Things**: Test the tool using different inputs, templates, and formulas to see what you can achieve.