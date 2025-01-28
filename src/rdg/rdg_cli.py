import sys
import os
from .parser import process_rdg_file
if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Usage: rdg.py <rdg_file>", file=sys.stderr)
        sys.exit(1)
    
    rdg_file = sys.argv[1]
    file_dir = os.path.dirname(os.path.abspath(rdg_file))  # get folder of rdg file
    process_rdg_file(rdg_file, file_dir)
    print("Rdg file parsed succesfully")