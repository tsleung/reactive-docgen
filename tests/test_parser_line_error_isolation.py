"""A bad line must not abandon the rest of the file, and must not report success.

Before this fix, `parse_rdg_line` was called outside the per-line `try`, so one malformed line or
unknown formula raised past the loop to the file-level handler. Every remaining step was silently
skipped and the CLI still printed that the file had been parsed successfully, exiting 0.

Hermetic: only deterministic formulas, no network, no model call.
"""

import os
import subprocess
import sys
import tempfile
import unittest

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


class LineErrorIsolation(unittest.TestCase):
    def _run(self, rdg_body, files):
        """Write an .rdg plus its inputs into a temp dir and run the CLI over it."""
        tmp = tempfile.mkdtemp()
        for name, content in files.items():
            path = os.path.join(tmp, name)
            os.makedirs(os.path.dirname(path), exist_ok=True)
            with open(path, "w") as handle:
                handle.write(content)
        rdg = os.path.join(tmp, "t.rdg")
        with open(rdg, "w") as handle:
            handle.write(rdg_body)
        # Prepend rather than replace: an inherited PYTHONPATH may carry the venv's own entries.
        inherited = os.environ.get("PYTHONPATH", "")
        env = dict(os.environ, PYTHONPATH=REPO + (os.pathsep + inherited if inherited else ""))
        proc = subprocess.run(
            [sys.executable, "-m", "src.rdg.rdg_cli", rdg],
            cwd=REPO, env=env, capture_output=True, text=True,
        )
        return tmp, proc

    def test_a_malformed_line_does_not_abandon_later_steps(self):
        # Line 2 is missing its closing paren. Line 3 is valid and must still run.
        tmp, proc = self._run(
            'out/a.md=FILESTOMARKDOWN(files="a.md")\n'
            'out/b.md=FILESTOMARKDOWN(files="a.md"\n'
            'out/c.md=FILESTOMARKDOWN(files="c.md")\n',
            {"a.md": "alpha\n", "c.md": "gamma\n"},
        )
        self.assertTrue(os.path.exists(os.path.join(tmp, "out/a.md")), "step before the bad line")
        self.assertTrue(
            os.path.exists(os.path.join(tmp, "out/c.md")),
            "step AFTER the bad line must still run; it was silently skipped before this fix",
        )
        with open(os.path.join(tmp, "out/c.md")) as handle:
            self.assertIn("gamma", handle.read())
        self.assertNotEqual(proc.returncode, 0, "a failed step must not exit 0")

    def test_unknown_formula_does_not_abandon_later_steps(self):
        # Formula names are case-sensitive; the second line names one that does not exist. Before
        # the fix this raised KeyError, and the handler then raised UnboundLocalError on the
        # not-yet-assigned output_path, taking the rest of the file with it.
        tmp, proc = self._run(
            'out/a.md=FILESTOMARKDOWN(files="a.md")\n'
            'out/b.md=NoSuchFormula(files="a.md")\n'
            'out/c.md=FILESTOMARKDOWN(files="c.md")\n',
            {"a.md": "alpha\n", "c.md": "gamma\n"},
        )
        self.assertTrue(os.path.exists(os.path.join(tmp, "out/c.md")), "step after unknown formula")
        self.assertNotEqual(proc.returncode, 0)

    def test_a_clean_file_still_succeeds(self):
        tmp, proc = self._run(
            'out/a.md=FILESTOMARKDOWN(files="a.md")\n',
            {"a.md": "alpha\n"},
        )
        self.assertTrue(os.path.exists(os.path.join(tmp, "out/a.md")))
        self.assertEqual(proc.returncode, 0, proc.stderr)


if __name__ == "__main__":
    unittest.main()
