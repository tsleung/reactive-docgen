"""RDG_JOBS — dependency-scheduled execution must be a provable reordering of serial, or serial.

Contract under test:
  - RDG_JOBS unset: byte-identical serial behavior (the loop object code is untouched).
  - RDG_JOBS=N: steps run in dependency waves; artifacts are byte-identical to a serial run.
  - RDG_JOBS=plan: prints the waves, executes nothing, writes nothing.
  - Anything unprovable — duplicate destination, forward reference, unparseable line — falls back
    to the serial loop, loudly, with the reason on stderr.
  - A failed step's dependents still run and read its ## ERROR bytes (parity with the serial loop).
  - The read-fence raises the moment a step reads another step's destination without an edge.

Hermetic: deterministic formulas only, no network, no model call.
"""

import os
import subprocess
import sys
import tempfile
import unittest

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _run(tmp, rdg_body, files, jobs=None):
    for name, content in files.items():
        path = os.path.join(tmp, name)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w") as handle:
            handle.write(content)
    rdg = os.path.join(tmp, "t.rdg")
    with open(rdg, "w") as handle:
        handle.write(rdg_body)
    env = dict(os.environ)
    inherited = env.get("PYTHONPATH", "")
    env["PYTHONPATH"] = REPO + (os.pathsep + inherited if inherited else "")
    if jobs is None:
        env.pop("RDG_JOBS", None)
    else:
        env["RDG_JOBS"] = str(jobs)
    return subprocess.run(
        [sys.executable, "-m", "src.rdg.rdg_cli", rdg],
        cwd=REPO, env=env, capture_output=True, text=True,
    )


def _artifacts(tmp):
    out = {}
    for root, _dirs, names in os.walk(os.path.join(tmp, "out")):
        for n in names:
            p = os.path.join(root, n)
            out[os.path.relpath(p, tmp)] = open(p).read()
    return out


# The review.rdg shape: independent gather->consume pairs chained only by destination strings.
# CREATEFILE renders {{placeholders}} from its other args, each resolved by process_input — so
# consumer content proves it read the producer's FRESH bytes, not a stale or absent file.
CHAIN = (
    'out/a.md=FILESTOMARKDOWN(files="src_a.md")\n'
    'out/b.md=FILESTOMARKDOWN(files="src_b.md")\n'
    'out/ca.md=CREATEFILE(content="consumed:{{x}}", x=out/a.md)\n'
    'out/cb.md=CREATEFILE(content="consumed:{{x}}", x=out/b.md)\n'
)
CHAIN_FILES = {"src_a.md": "alpha-marker\n", "src_b.md": "beta-marker\n"}


class GoldenSerialEqualsParallel(unittest.TestCase):
    def test_artifacts_byte_identical_and_fresh(self):
        t1 = tempfile.mkdtemp()
        serial = _run(t1, CHAIN, CHAIN_FILES)
        self.assertEqual(serial.returncode, 0, serial.stderr)
        golden = _artifacts(t1)

        t2 = tempfile.mkdtemp()
        parallel = _run(t2, CHAIN, CHAIN_FILES, jobs=4)
        self.assertEqual(parallel.returncode, 0, parallel.stderr)
        self.assertEqual(golden, _artifacts(t2), "parallel must be a reordering, not a rewrite")

        # Wave correctness: the consumer embedded the producer's marker, so it read fresh bytes.
        self.assertIn("alpha-marker", golden["out/ca.md"])
        self.assertIn("beta-marker", golden["out/cb.md"])
        self.assertNotIn("out/a.md", golden["out/ca.md"], "a pasted path means the read raced the write")


class RefuseToSerial(unittest.TestCase):
    def test_forward_reference_falls_back(self):
        body = (
            'out/first.md=CREATEFILE(content="{{x}}", x=out/second.md)\n'
            'out/second.md=FILESTOMARKDOWN(files="src_a.md")\n'
        )
        t = tempfile.mkdtemp()
        parallel = _run(t, body, CHAIN_FILES, jobs=4)
        self.assertIn("serial fallback", parallel.stderr)
        self.assertIn("forward reference", parallel.stderr)
        t2 = tempfile.mkdtemp()
        serial = _run(t2, body, CHAIN_FILES)
        self.assertEqual(_artifacts(t), _artifacts(t2), "fallback must equal plain serial")

    def test_duplicate_destination_falls_back(self):
        body = (
            'out/x.md=FILESTOMARKDOWN(files="src_a.md")\n'
            'out/x.md=FILESTOMARKDOWN(files="src_b.md")\n'
        )
        t = tempfile.mkdtemp()
        parallel = _run(t, body, CHAIN_FILES, jobs=4)
        self.assertIn("duplicate destination", parallel.stderr)
        t2 = tempfile.mkdtemp()
        serial = _run(t2, body, CHAIN_FILES)
        self.assertEqual(_artifacts(t), _artifacts(t2))


class Barriers(unittest.TestCase):
    def test_walker_is_a_barrier_in_the_plan(self):
        body = (
            'out/a.md=FILESTOMARKDOWN(files="src_a.md")\n'
            'out/g.md=GLOBTOMARKDOWN(pattern="src_*.md")\n'
            'out/b.md=FILESTOMARKDOWN(files="src_b.md")\n'
        )
        t = tempfile.mkdtemp()
        plan = _run(t, body, CHAIN_FILES, jobs="plan")
        self.assertEqual(plan.returncode, 0, plan.stderr)
        self.assertIn("[barrier]", plan.stdout)
        # Three waves: the barrier fences its neighbours into separate waves.
        self.assertIn("wave 2:", plan.stdout)
        # plan mode executes nothing
        self.assertFalse(os.path.exists(os.path.join(t, "out")), "plan mode must not write")

    def test_barrier_execution_is_ordered_around(self):
        # The glob step must see BOTH earlier destinations if they matched its pattern — here it
        # globs the sources, so the assertion is simply byte-parity with serial.
        body = (
            'out/a.md=FILESTOMARKDOWN(files="src_a.md")\n'
            'out/g.md=GLOBTOMARKDOWN(pattern="src_*.md")\n'
            'out/b.md=FILESTOMARKDOWN(files="src_b.md")\n'
        )
        t1, t2 = tempfile.mkdtemp(), tempfile.mkdtemp()
        serial = _run(t1, body, CHAIN_FILES)
        parallel = _run(t2, body, CHAIN_FILES, jobs=4)
        self.assertEqual(serial.returncode, 0, serial.stderr)
        self.assertEqual(parallel.returncode, 0, parallel.stderr)
        self.assertEqual(_artifacts(t1), _artifacts(t2))


class FailureParity(unittest.TestCase):
    def test_failed_steps_dependents_still_run(self):
        # Step 1 fails at RUN time (unmatched template placeholder — the parse is fine, so the
        # file genuinely plans and runs in waves rather than falling back). Its handler writes
        # ## ERROR into its own destination; step 2 depends on that destination and must still
        # run, reading the error bytes — exactly the serial contract from the error-isolation PR.
        body = (
            'out/bad.md=CREATEFILE(content="{{missing}}", x=src_a.md)\n'
            'out/consumer.md=CREATEFILE(content="got:{{x}}", x=out/bad.md)\n'
        )
        t1, t2 = tempfile.mkdtemp(), tempfile.mkdtemp()
        serial = _run(t1, body, CHAIN_FILES)
        parallel = _run(t2, body, CHAIN_FILES, jobs=4)
        self.assertEqual(serial.returncode, 1)
        self.assertEqual(parallel.returncode, 1)
        # a real plan ran — no fallback notice
        self.assertNotIn("serial fallback", parallel.stderr)
        self.assertEqual(_artifacts(t1), _artifacts(t2))
        self.assertIn("## ERROR", _artifacts(t2)["out/consumer.md"])

    def test_unknown_formula_is_a_parse_failure_and_falls_back(self):
        # An unknown formula fails at PARSE, so the plan cannot be built: parallel mode must fall
        # back to the serial loop and reproduce its exact semantics (no destination written; a
        # consumer receives the literal path string, because that is what process_input does with
        # a nonexistent file).
        body = (
            'out/bad.md=NOSUCHFORMULA(files="src_a.md")\n'
            'out/consumer.md=CREATEFILE(content="{{x}}", x=out/bad.md)\n'
        )
        t1, t2 = tempfile.mkdtemp(), tempfile.mkdtemp()
        serial = _run(t1, body, CHAIN_FILES)
        parallel = _run(t2, body, CHAIN_FILES, jobs=4)
        self.assertEqual(serial.returncode, 1)
        self.assertEqual(parallel.returncode, 1)
        self.assertIn("serial fallback", parallel.stderr)
        self.assertEqual(_artifacts(t1), _artifacts(t2))
        self.assertEqual(_artifacts(t2)["out/consumer.md"], "out/bad.md")


class ReadFence(unittest.TestCase):
    def test_fence_raises_on_unedged_read(self):
        # Unit-level: arm the fence the way _run_step does, then read a destination that is not in
        # the allowed set. This is the detector for an edge the inference missed.
        sys.path.insert(0, REPO)
        from src.rdg.functions import process_input, _READ_FENCE, RdgParserError
        tmp = tempfile.mkdtemp()
        dest = os.path.join(tmp, "out", "a.md")
        os.makedirs(os.path.dirname(dest), exist_ok=True)
        with open(dest, "w") as handle:
            handle.write("bytes")
        fence = ({os.path.normpath(dest): "step 1 (out/a.md)"}, set(), "step 2 (out/b.md)")
        token = _READ_FENCE.set(fence)
        try:
            with self.assertRaises(RdgParserError) as ctx:
                process_input("out/a.md", tmp)
            self.assertIn("step 2", str(ctx.exception))
            self.assertIn("step 1", str(ctx.exception))
        finally:
            _READ_FENCE.reset(token)
        # And with the edge present, the same read succeeds.
        fence_ok = ({os.path.normpath(dest): "step 1 (out/a.md)"}, {os.path.normpath(dest)}, "step 2")
        token = _READ_FENCE.set(fence_ok)
        try:
            self.assertEqual(process_input("out/a.md", tmp), "bytes")
        finally:
            _READ_FENCE.reset(token)


if __name__ == "__main__":
    unittest.main()
