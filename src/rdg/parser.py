import re
import os
import sys
from concurrent.futures import ThreadPoolExecutor
from typing import Any
from .functions import FUNCTION_REGISTRY, RdgParserError, _READ_FENCE

def parse_rdg_line(line: str, file_dir: str = ".") -> tuple[str, str, dict[str, Any]]:
    """Parses a single line of the rdg file."""
    line = line.strip()
    if not line or line.startswith("#"):
        return None, None, None

    match = re.match(r"([^=]+)=([^()]+)\((.*)\)", line)
    if not match:
        raise RdgParserError(f"Invalid line format: {line}")

    output_file, formula_name, arguments_str = match.groups()
    output_file = output_file.strip()
    formula_name = formula_name.strip()

    if formula_name not in FUNCTION_REGISTRY:
        raise RdgParserError(f"Unknown formula: {formula_name}")

    arguments = {}
    # Regex to split on commas outside of quotes
    argument_pairs = re.split(r',\s*(?=(?:[^\"]*\"[^\"]*\")*[^\"]*$)', arguments_str)

    for arg_pair in argument_pairs:
        arg_pair = arg_pair.strip()
        if not arg_pair:
            continue
        arg_match = re.match(r"([^=]+)=(.*)", arg_pair)
        if not arg_match:
            raise RdgParserError(f"Invalid argument format: {arg_pair}")
        arg_name, arg_value = arg_match.groups()
        arg_name = arg_name.strip()
        arg_value = arg_value.strip()
        
        # check if string or file
        if (arg_value.startswith('"') and arg_value.endswith('"')) or (arg_value.startswith("'") and arg_value.endswith("'")):
            # string, so we strip it and handle escaped quotes
            arg_value = arg_value[1:-1]
            arg_value = arg_value.replace('\\"', '"').replace("\\'", "'")
            arguments[arg_name] = arg_value
        else:
            # file path so we expand it with file_dir and handle relative paths
            arguments[arg_name] = arg_value
            

    return output_file, formula_name, arguments


def _run_step(rdg_file: str, file_dir: str, line: str, fence=None) -> int:
    """Execute one line of an rdg file. Returns 1 if the step failed, else 0.

    This is the serial loop body, extracted verbatim so the serial path and the RDG_JOBS wave
    runner share one implementation — per-step semantics (parse inside the try, delete the
    destination before the formula runs, write ## ERROR into the step's own destination on
    failure) cannot drift between the two.

    `fence` is only ever set by the parallel runner: (all_destinations, allowed_destinations,
    step_label). It arms the read-fence in process_input for the duration of the formula call.
    ContextVars are per-thread, and this runs inside the worker thread, so arming it here
    scopes it to exactly this step.
    """
    output_path = None
    try:
        output_file, formula_name, arguments = parse_rdg_line(line, file_dir)
        if not output_file:  # skip empty lines or comments
            return 0

        # Resolved before the formula is looked up, so the error handlers always have a
        # path to write to. An unknown formula used to raise KeyError here, and the
        # handler then raised UnboundLocalError on output_path, aborting the file.
        output_path = os.path.join(file_dir, output_file)
        formula = FUNCTION_REGISTRY[formula_name]

        # Create the output directory if it doesn't exist
        output_dir = os.path.dirname(output_path)
        if output_dir and not os.path.exists(output_dir):
            os.makedirs(output_dir, exist_ok=True)

        # Delete the output file if it exists
        if os.path.exists(output_path):
            os.remove(output_path)

        if fence is not None:
            token = _READ_FENCE.set(fence)
            try:
                result = formula(rdg_file, **arguments)
            finally:
                _READ_FENCE.reset(token)
        else:
            result = formula(rdg_file, **arguments)

        with open(output_path, 'w') as outfile:
            outfile.write(result)
        return 0
    except KeyError as e:
        print(f"Unknown formula on line '{line.strip()}': {e}", file=sys.stderr)
        _write_error(output_path, f"Unknown formula: {e}")
        return 1
    except RdgParserError as e:
        print(f"Error processing line '{line.strip()}': {e}", file=sys.stderr)
        _write_error(output_path, e)
        return 1
    except Exception as e:
        print(f"An unexpected error occurred processing line '{line.strip()}': {e}", file=sys.stderr)
        _write_error(output_path, e)
        return 1


def process_rdg_file(rdg_file: str, file_dir: str = ".") -> int:
    """Process the given rdg file. Returns the number of steps that failed."""
    failures = 0
    try:
        with open(rdg_file, 'r') as f:
            for line in f:
                # Parsing happens INSIDE the per-line try (in _run_step). Outside it, a single
                # malformed line or unknown formula raised past the loop to the file-level handler
                # below, which silently abandoned every remaining line — and the CLI still
                # reported success.
                failures += _run_step(rdg_file, file_dir, line)
    except FileNotFoundError:
        print(f"Error: RDF file not found at '{rdg_file}'", file=sys.stderr)
        return 1
    except Exception as e:
        print(f"An unexpected error occurred: {e}", file=sys.stderr)
        return 1
    return failures


def _write_error(output_path, error):
    """Record the error in the step's own output so downstream consumers see it.

    `output_path` is None when the line never parsed far enough to name a destination; there is
    nowhere to write, and stderr already carries the reason.
    """
    if output_path is None:
        return
    try:
        with open(output_path, 'w') as outfile:
            outfile.write(f"## ERROR\n\n{error}\n")
    except OSError as exc:
        print(f"Could not write error to '{output_path}': {exc}", file=sys.stderr)


# ---------------------------------------------------------------------------
# RDG_JOBS — dependency-scheduled execution
# ---------------------------------------------------------------------------
#
# Top-to-bottom stays the AUTHORING contract: a step that gathers is written above the step that
# consumes it, and that is all an author ever has to know. What follows lets the ENGINE notice when
# line order over-serializes — five independent model calls in a row cost 5x wall clock for no
# reason — and run independent steps concurrently, without the author declaring anything.
#
# Opt-in via RDG_JOBS=N (see rdg_cli.py). Unset, the serial loop above runs untouched.
#
# The rules are purely mechanical, and everything they cannot prove falls back to the serial loop:
#
#   EDGE      step j depends on step i when one of j's argument values (split on commas, each piece
#             path-normalized) equals i's normalized destination. That is exactly the join the
#             engine itself performs at run time: process_input resolves an argument against the
#             file's directory and reads it if it exists.
#   BARRIER   a step whose formula is not in KNOWN_SAFE runs alone — after everything before it,
#             before everything after it. KNOWN_SAFE holds only formulas verified to read the
#             filesystem exclusively through paths named in their argument values. Everything else
#             — the glob/directory walkers, and every externally loaded formula — reads things its
#             arguments do not name, so its true edges are unknowable from the text.
#   REFUSE    a duplicate destination, a forward reference (an argument naming a LATER step's
#             destination), or any unparseable line -> the whole file runs serially, with the
#             reason on stderr. Serial has defined semantics for all three; a reordering does not.
#
# Every edge goes from a lower index to a higher one and forward references are refused, so the
# graph is acyclic by construction — there is no cycle detection because no cycle can be built.
#
# WHY THE CAUTION IS NOT OPTIONAL. A missed edge here does not crash. The engine deletes a
# destination before writing it, and process_input treats a nonexistent path as literal text — so
# a consumer scheduled before its producer either reads the previous run's stale bytes or pastes
# the path string itself into a prompt, gets a fluent answer, exits 0, and caches the wrong result
# under the wrong prompt. GNU Make shipped parallel builds in the 1980s and its missed-edge
# detector (--shuffle) in 2022; the fence in process_input ships here in the same commit.

KNOWN_SAFE = {
    "FILESTOMARKDOWN", "GEMINIPROMPT", "GEMINIPROMPTFILE", "CREATEFILE",
    "CREATEGEMINIPROMPT", "SUMMARIZE", "UPPERCASE",
}


def plan_rdg_file(rdg_file: str, file_dir: str = "."):
    """Derive the wave plan for a file, or the reason it must run serially.

    Returns (steps, waves, edges, reason). `reason` is None when the plan is usable; otherwise it
    says why the file falls back to the serial loop, and the other fields describe what WAS parsed.
    steps: list of dicts {index, line, dest, norm, formula}. waves: list of lists of step indexes.
    edges: set of (i, j) pairs meaning i must complete before j starts.
    """
    def norm(p):
        return os.path.normpath(os.path.join(file_dir, p))

    steps = []
    with open(rdg_file, 'r') as f:
        for raw in f:
            stripped = raw.strip()
            if not stripped or stripped.startswith("#"):
                continue
            try:
                dest, formula_name, arguments = parse_rdg_line(raw, file_dir)
            except RdgParserError as e:
                return steps, [], set(), f"line will not parse ({e})"
            if not dest:
                continue
            steps.append({
                "index": len(steps), "line": raw, "dest": dest, "norm": norm(dest),
                "formula": formula_name, "args": arguments,
            })

    by_norm = {}
    for s in steps:
        if s["norm"] in by_norm:
            return steps, [], set(), f"duplicate destination '{s['dest']}'"
        by_norm[s["norm"]] = s["index"]

    edges = set()
    for s in steps:
        for value in s["args"].values():
            for piece in str(value).split(","):
                piece = piece.strip()
                if not piece:
                    continue
                producer = by_norm.get(norm(piece))
                if producer is None or producer == s["index"]:
                    continue
                if producer > s["index"]:
                    return steps, [], set(), (
                        f"forward reference: step {s['index'] + 1} reads '{piece}', "
                        f"written by later step {producer + 1}"
                    )
                edges.add((producer, s["index"]))

    for s in steps:
        if s["formula"] not in KNOWN_SAFE:
            for other in steps:
                if other["index"] < s["index"]:
                    edges.add((other["index"], s["index"]))
                elif other["index"] > s["index"]:
                    edges.add((s["index"], other["index"]))

    # Kahn layering. Acyclic by construction (every edge goes forward), so this always terminates.
    preds = {s["index"]: set() for s in steps}
    for i, j in edges:
        preds[j].add(i)
    waves, placed = [], set()
    while len(placed) < len(steps):
        wave = [i for i in preds if i not in placed and preds[i] <= placed]
        waves.append(sorted(wave))
        placed.update(wave)

    return steps, waves, edges, None


def print_plan(rdg_file: str, file_dir: str = ".") -> int:
    """RDG_JOBS=plan — show what would run in which wave. Executes nothing, writes nothing."""
    try:
        steps, waves, edges, reason = plan_rdg_file(rdg_file, file_dir)
    except FileNotFoundError:
        print(f"Error: RDF file not found at '{rdg_file}'", file=sys.stderr)
        return 1
    if reason is not None:
        print(f"serial fallback: {reason}")
        return 0
    preds = {s["index"]: sorted(i for i, j in edges if j == s["index"]) for s in steps}
    for w, wave in enumerate(waves):
        print(f"wave {w}:")
        for i in wave:
            s = steps[i]
            kind = "safe" if s["formula"] in KNOWN_SAFE else "barrier"
            after = f"  after {[p + 1 for p in preds[i]]}" if preds[i] else ""
            print(f"  step {i + 1}  {s['formula']:<16} -> {s['dest']}  [{kind}]{after}")
    return 0


def process_rdg_file_parallel(rdg_file: str, file_dir: str = ".", jobs: int = 2) -> int:
    """Wave-scheduled execution. Falls back to the serial loop whenever the plan cannot be proven.

    Semantics are the serial loop's, re-ordered only where the plan proves independence: the same
    _run_step body, a failed step still writes ## ERROR into its own destination, and its
    dependents still run afterward and read those bytes — exactly as they would serially.
    """
    try:
        steps, waves, edges, reason = plan_rdg_file(rdg_file, file_dir)
    except FileNotFoundError:
        print(f"Error: RDF file not found at '{rdg_file}'", file=sys.stderr)
        return 1
    except Exception as e:
        print(f"An unexpected error occurred: {e}", file=sys.stderr)
        return 1
    if reason is not None:
        print(f"RDG_JOBS: serial fallback — {reason}", file=sys.stderr)
        return process_rdg_file(rdg_file, file_dir)

    # For the read-fence: what each step is ALLOWED to read is its transitive predecessors'
    # destinations (plus its own, which it just deleted). Reading any OTHER step's destination
    # means the edge inference missed a dependency — that must be loud, never a stale read.
    ancestors = {s["index"]: set() for s in steps}
    for wave in waves:
        for j in wave:
            for i, k in edges:
                if k == j:
                    ancestors[j].add(i)
                    ancestors[j] |= ancestors[i]
    all_dests = {s["norm"]: f"step {s['index'] + 1} ({s['dest']})" for s in steps}

    failures = 0
    with ThreadPoolExecutor(max_workers=max(2, jobs)) as pool:
        for wave in waves:
            futures = []
            for i in wave:
                s = steps[i]
                allowed = {steps[a]["norm"] for a in ancestors[i]} | {s["norm"]}
                fence = (all_dests, allowed, f"step {i + 1} ({s['dest']})")
                futures.append(pool.submit(_run_step, rdg_file, file_dir, s["line"], fence))
            for fut in futures:
                failures += fut.result()
    return failures