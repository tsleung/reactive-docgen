"""RDG_EVENTS=jsonl — structured step events on stderr, opt-in, both runners.

Contract under test:
  - env absent: zero event lines (the feature is invisible — nothing else changes).
  - RDG_EVENTS=jsonl: one step_start + one step_end per real step on STDERR, each line valid
    JSON, with 1-based i/n progress, dest, formula; stdout untouched.
  - a failing step emits step_end ok=false with the destination in wrote (## ERROR bytes are
    still a write); a consumer can distinguish created content from recorded failure.
  - RDG_JOBS wave runner emits the same events (shared _run_step emission).
Hermetic: deterministic formulas only.
"""

import json
import os
import subprocess
import sys
import tempfile
import unittest

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _run(tmp, rdg_body, env_extra=None):
    for name in ("in1.txt", "in2.txt"):
        with open(os.path.join(tmp, name), "w") as handle:
            handle.write(name)
    rdg = os.path.join(tmp, "t.rdg")
    with open(rdg, "w") as handle:
        handle.write(rdg_body)
    env = dict(os.environ)
    inherited = env.get("PYTHONPATH", "")
    env["PYTHONPATH"] = REPO + (os.pathsep + inherited if inherited else "")
    env.pop("RDG_EVENTS", None)
    env.pop("RDG_LOG_FILE", None)
    if env_extra:
        env.update(env_extra)
    return subprocess.run(
        [sys.executable, "-m", "src.rdg.rdg_cli", rdg],
        capture_output=True, text=True, env=env, cwd=tmp,
    )


def _events(stderr):
    out = []
    for line in stderr.splitlines():
        line = line.strip()
        if line.startswith("{"):
            try:
                obj = json.loads(line)
            except json.JSONDecodeError:
                continue
            if "ev" in obj:
                out.append(obj)
    return out


BODY = "out/a.md=UPPERCASE(file=in1.txt)\n# comment\nout/b.md=UPPERCASE(file=in2.txt)\n"


class EventsOptIn(unittest.TestCase):
    def test_absent_env_emits_nothing(self):
        with tempfile.TemporaryDirectory() as tmp:
            r = _run(tmp, BODY)
            self.assertEqual(_events(r.stderr), [])

    def test_jsonl_emits_start_end_per_step_with_progress(self):
        with tempfile.TemporaryDirectory() as tmp:
            r = _run(tmp, BODY, {"RDG_EVENTS": "jsonl"})
            evs = _events(r.stderr)
            starts = [e for e in evs if e["ev"] == "step_start"]
            ends = [e for e in evs if e["ev"] == "step_end"]
            self.assertEqual(len(starts), 2)
            self.assertEqual(len(ends), 2)
            self.assertEqual([e["i"] for e in starts], [1, 2])
            self.assertTrue(all(e["n"] == 2 for e in starts))
            self.assertEqual(starts[0]["dest"], "out/a.md")
            self.assertEqual(starts[0]["formula"], "UPPERCASE")
            self.assertTrue(all(e["ok"] for e in ends))
            self.assertEqual(ends[0]["wrote"], ["out/a.md"])

    def test_failing_step_emits_ok_false_with_wrote(self):
        with tempfile.TemporaryDirectory() as tmp:
            r = _run(tmp, "out/bad.md=UPPERCASE(nope=1)\n", {"RDG_EVENTS": "jsonl"})
            ends = [e for e in _events(r.stderr) if e["ev"] == "step_end"]
            self.assertEqual(len(ends), 1)
            self.assertFalse(ends[0]["ok"])
            self.assertEqual(ends[0]["wrote"], ["out/bad.md"])

    def test_wave_runner_emits_same_shape(self):
        with tempfile.TemporaryDirectory() as tmp:
            r = _run(tmp, BODY, {"RDG_EVENTS": "jsonl", "RDG_JOBS": "2"})
            evs = _events(r.stderr)
            self.assertEqual(len([e for e in evs if e["ev"] == "step_start"]), 2)
            ends = [e for e in evs if e["ev"] == "step_end"]
            self.assertEqual(len(ends), 2)
            self.assertTrue(all(e["n"] == 2 for e in ends))

    def test_log_file_records_events(self):
        with tempfile.TemporaryDirectory() as tmp:
            log = os.path.join(tmp, "run.log")
            _run(tmp, BODY, {"RDG_LOG_FILE": log})
            with open(log) as handle:
                content = handle.read()
            self.assertIn("step_start", content)
            self.assertIn("out/a.md", content)


if __name__ == "__main__":
    unittest.main()
