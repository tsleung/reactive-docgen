import os
import time
import subprocess
import logging
import argparse

LOG_FORMAT = '%(asctime)s - %(levelname)s - %(message)s'
logging.basicConfig(level=logging.INFO, format=LOG_FORMAT)

THROTTLE_SECONDS = 1

def run_command(cmd):
    """Runs a shell command and logs the result."""
    try:
        result = subprocess.run(cmd, shell=True, capture_output=True, text=True, check=True)
        logging.info(f"Command '{cmd}' successful:\n{result.stdout}")
    except subprocess.CalledProcessError as e:
        logging.error(f"Command '{cmd}' failed (return code {e.returncode}):\n{e.stderr}")
    except Exception as e:
        logging.exception(f"Unexpected error running command '{cmd}': {e}")


def watch_directory(path, command):
    """Watches the specified directory and runs the command when modified."""
    last_run = 0
    while True:
        try:
            max_modified_time = 0  # Keep track of the latest modification time
            for root, _, files in os.walk(path):  # Recursively walk the directory tree
                for file in files:
                    filepath = os.path.join(root, file)
                    try:
                        modified_time = os.stat(filepath).st_mtime
                        max_modified_time = max(max_modified_time, modified_time)  # Update latest time
                    except OSError as e:  # Handle potential permission errors, etc. during file access.
                        logging.error(f"OSError accessing file '{filepath}': {e}")

            if time.time() - last_run > THROTTLE_SECONDS and max_modified_time > last_run:
                logging.info(f"Change detected in '{path}'. Running command.")
                run_command(command)
                last_run = time.time()

            time.sleep(0.2)  # Adjust as needed

        except KeyboardInterrupt:
            logging.info("Watcher stopped.")
            break
        except OSError as e:
            logging.error(f"Error accessing directory '{path}': {e}")
            break
        except Exception as e:
            logging.exception(f"Unexpected error: {e}")
            break

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description='Watch a directory and run a shell command when modified.')
    parser.add_argument('path', help='Path to the directory to watch.')
    parser.add_argument('command', help='Shell command to run.')
    args = parser.parse_args()
    watch_directory(args.path, args.command)