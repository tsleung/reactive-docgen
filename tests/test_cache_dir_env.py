#!/usr/bin/env python3
"""RDG_CACHE_DIR — choose the response cache location explicitly.

Contract:
  - Unset, the cache directory is `.gemini_cache` relative to the process cwd (unchanged).
  - Set, the cache directory is exactly that path, and nothing is created in the cwd.

The directory is created at import of config.py, so these drive the real CLI in a subprocess with a
cwd of their own: that is the behaviour being tested, and it keeps the repo free of stray caches.

STRUCTURAL — no network, no LLM, no credentials.

Run (use the project venv):
  cd rdg-notebook/reactive-docgen
  .venv/bin/python -m pytest tests/test_cache_dir_env.py -v
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent


def _run_in(cwd: Path, cache_dir: str | None):
    """Run a trivial deterministic pipeline with `cwd` as the process working directory."""
    (cwd / "out").mkdir(exist_ok=True)
    (cwd / "a.md").write_text("alpha\n")
    rdg = cwd / "t.rdg"
    rdg.write_text('out/a.md=FILESTOMARKDOWN(files="a.md")\n')

    env = dict(os.environ)
    inherited = env.get("PYTHONPATH", "")
    env["PYTHONPATH"] = str(REPO) + (os.pathsep + inherited if inherited else "")
    if cache_dir is None:
        env.pop("RDG_CACHE_DIR", None)
    else:
        env["RDG_CACHE_DIR"] = cache_dir

    proc = subprocess.run(
        [sys.executable, "-m", "src.rdg.rdg_cli", str(rdg)],
        cwd=cwd, env=env, capture_output=True, text=True,
    )
    assert proc.returncode == 0, proc.stderr
    return proc


def test_default_is_unchanged(tmp_path):
    """Unset, the cache still lands in the cwd — this PR must not move anyone's cache."""
    _run_in(tmp_path, None)
    assert (tmp_path / ".gemini_cache").is_dir()


def test_env_var_relocates_the_cache(tmp_path):
    elsewhere = tmp_path / "chosen-cache"
    _run_in(tmp_path, str(elsewhere))

    assert elsewhere.is_dir(), "the cache should be created at the requested path"
    assert not (tmp_path / ".gemini_cache").exists(), "nothing should be created in the cwd"


def test_two_cwds_can_share_one_cache(tmp_path):
    """The point of the variable: cache scope stops being an accident of where you started."""
    shared = tmp_path / "shared-cache"
    one, two = tmp_path / "one", tmp_path / "two"
    one.mkdir(), two.mkdir()

    _run_in(one, str(shared))
    _run_in(two, str(shared))

    assert shared.is_dir()
    assert not (one / ".gemini_cache").exists()
    assert not (two / ".gemini_cache").exists()
