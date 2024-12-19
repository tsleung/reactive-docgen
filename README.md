# reactive-docgen
Generate docs reactively

```
pip install google-generativeai
```
## Virtual Env
```
python3 -m venv .venv
```
```
source .venv/bin/activate

```
```
python script-watcher.py . scripts/hello-world.sh 
```
```
export GEMINI_API_KEY=$GEMINI_API_KEY
```
## Demo
To run the sample.rdg, run
```
python src/rdg.py sample.rdg
```

To run it with a watcher
```
python src/script-watcher.py . ./sample.rdg.sh
```

## Script Watcher
### Permissions Issue for Scripts
The "permission denied" error means that the script sample.rdg.sh doesn't have execute permission. You need to make it executable using the chmod command:
```
chmod +x sample.rdg.sh
```
Here's how you can grant execute permission recursively:
```
chmod -R +x /path/to/your/directory
```
A more targeted and safer approach is to grant execute permission only to files ending in .sh (or whatever extension you use for your shell scripts):

```
find /path/to/your/directory -name "*.sh" -exec chmod +x {} \;
```

If you have scripts using different interpreters (e.g., Bash, Python, etc.), you can use find with more specific criteria:
```
find /path/to/your/directory \( -name "*.sh" -o -name "*.py" \) -exec chmod +x {} \;

```