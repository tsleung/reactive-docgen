#!/usr/bin/env python3
"""RDG_FORMULA_PATH — load formulas from outside the package.

Contract:
  - Every module in a RDG_FORMULA_PATH directory exporting `FORMULAS: Dict[str, Callable]`
    is merged into FUNCTION_REGISTRY, and its formulas are callable from an .rdg file.
  - Multiple directories are separated by os.pathsep.
  - Modules starting with `_` are skipped; non-.py entries are ignored.
  - Loading is FAIL-LOUD: a path that is not a directory, a module that will not import, or a
    module without a FORMULAS dict raises rather than being skipped. Skipping would leave the
    formula undefined and surface later as "unknown formula", sending the reader to their .rdg
    to debug a typo that is not there.
  - With the variable unset the registry is unchanged.

Loading happens at import of functions.py, so these drive the real CLI in a subprocess: that
exercises the actual wiring rather than calling the private loader directly.

STRUCTURAL — no network, no LLM, no credentials.

Run (use the project venv):
  cd rdg-notebook/reactive-docgen
  .venv/bin/python -m pytest tests/test_formula_path.py -v
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent

FORMULA_MODULE = '''
"""A formula defined outside the engine package."""

def shout(rdg_file, **kwargs):
    return "SHOUTED: " + kwargs.get("text", "").upper()

FORMULAS = {"SHOUT": shout}
'''


def _run_cli(rdg_path: Path, formula_path: str | None):
    env = dict(os.environ)
    inherited = env.get("PYTHONPATH", "")
    env["PYTHONPATH"] = str(REPO) + (os.pathsep + inherited if inherited else "")
    if formula_path is None:
        env.pop("RDG_FORMULA_PATH", None)
    else:
        env["RDG_FORMULA_PATH"] = formula_path
    return subprocess.run(
        [sys.executable, "-m", "src.rdg.rdg_cli", str(rdg_path)],
        cwd=REPO, env=env, capture_output=True, text=True,
    )


def _rdg(tmp_path: Path, body: str) -> Path:
    (tmp_path / "out").mkdir(exist_ok=True)
    rdg = tmp_path / "t.rdg"
    rdg.write_text(body)
    return rdg


def test_external_formula_is_callable(tmp_path):
    formulas = tmp_path / "formulas"
    formulas.mkdir()
    (formulas / "shout.py").write_text(FORMULA_MODULE)

    rdg = _rdg(tmp_path, 'out/a.md=SHOUT(text="hello")\n')
    proc = _run_cli(rdg, str(formulas))

    assert proc.returncode == 0, proc.stderr
    assert (tmp_path / "out/a.md").read_text() == "SHOUTED: HELLO"


def test_unset_leaves_the_formula_unknown(tmp_path):
    """The same .rdg without the env var — proves the formula came from the path, not the engine."""
    formulas = tmp_path / "formulas"
    formulas.mkdir()
    (formulas / "shout.py").write_text(FORMULA_MODULE)

    rdg = _rdg(tmp_path, 'out/a.md=SHOUT(text="hello")\n')
    proc = _run_cli(rdg, None)

    # Asserted on the artifact and the message, not the exit code: an unknown formula mid-file
    # still exits 0 on this branch. That is a separate parser defect, fixed in the per-line error
    # isolation PR; asserting it here would make this test fail for a reason it does not own.
    assert not (tmp_path / "out/a.md").exists()
    assert "Unknown formula" in proc.stderr


def test_multiple_directories(tmp_path):
    one, two = tmp_path / "one", tmp_path / "two"
    one.mkdir(), two.mkdir()
    (one / "shout.py").write_text(FORMULA_MODULE)
    (two / "whisper.py").write_text(
        'def whisper(rdg_file, **kwargs):\n'
        '    return "whispered: " + kwargs.get("text", "").lower()\n'
        'FORMULAS = {"WHISPER": whisper}\n'
    )

    rdg = _rdg(tmp_path, 'out/a.md=SHOUT(text="hi")\nout/b.md=WHISPER(text="HI")\n')
    proc = _run_cli(rdg, os.pathsep.join([str(one), str(two)]))

    assert proc.returncode == 0, proc.stderr
    assert (tmp_path / "out/a.md").read_text() == "SHOUTED: HI"
    assert (tmp_path / "out/b.md").read_text() == "whispered: hi"


def test_underscore_modules_are_skipped(tmp_path):
    formulas = tmp_path / "formulas"
    formulas.mkdir()
    (formulas / "shout.py").write_text(FORMULA_MODULE)
    # A private helper with no FORMULAS dict. If it were loaded, fail-loud would raise and the
    # valid module beside it would never register.
    (formulas / "_helper.py").write_text("VALUE = 1\n")

    rdg = _rdg(tmp_path, 'out/a.md=SHOUT(text="hi")\n')
    proc = _run_cli(rdg, str(formulas))

    assert proc.returncode == 0, proc.stderr
    assert (tmp_path / "out/a.md").read_text() == "SHOUTED: HI"


def test_missing_directory_fails_loud(tmp_path):
    rdg = _rdg(tmp_path, 'out/a.md=SHOUT(text="hi")\n')
    proc = _run_cli(rdg, str(tmp_path / "does-not-exist"))

    assert proc.returncode != 0
    assert "RDG_FORMULA_PATH" in proc.stderr


def test_module_without_formulas_dict_fails_loud(tmp_path):
    formulas = tmp_path / "formulas"
    formulas.mkdir()
    (formulas / "broken.py").write_text("VALUE = 1\n")

    rdg = _rdg(tmp_path, 'out/a.md=SHOUT(text="hi")\n')
    proc = _run_cli(rdg, str(formulas))

    assert proc.returncode != 0
    assert "FORMULAS" in proc.stderr
