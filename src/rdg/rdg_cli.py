import sys
import os
from .parser import process_rdg_file, process_rdg_file_parallel, print_plan
if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Usage: rdg.py <rdg_file>", file=sys.stderr)
        sys.exit(1)

    rdg_file = sys.argv[1]
    file_dir = os.path.dirname(os.path.abspath(rdg_file))  # get folder of rdg file

    # RDG_JOBS opts into dependency-scheduled execution (see parser.py). Unset or 1, the serial
    # loop runs exactly as it always has. "plan" prints the derived waves and executes nothing.
    jobs_env = os.environ.get("RDG_JOBS", "").strip()
    if jobs_env == "plan":
        sys.exit(print_plan(rdg_file, file_dir))
    jobs = int(jobs_env) if jobs_env.isdigit() else 1
    if jobs > 1:
        failures = process_rdg_file_parallel(rdg_file, file_dir, jobs)
    else:
        failures = process_rdg_file(rdg_file, file_dir)
    if failures:
        print(f"Rdg file processed with {failures} failed step(s)", file=sys.stderr)
        sys.exit(1)
    print("Rdg file processed successfully")
