#!/usr/bin/env python3
"""
RDG Engine — RDG_PRIMARY=claude end-to-end regression test.

WorkGraph: wo-task-rdg-engine-claude-e2e-test
ACC: rdg-notebook/reactive-docgen/ gains a test that exercises RDG_PRIMARY=claude
end-to-end on a minimal `.rdg` pipeline. Runs without GEMINI_API_KEY, stubs the
`claude` CLI, and proves no genai SDK call is made.

Design (hermetic, subprocess-driven — NO network, NO API key, NO real LLM):

The claude-primary branch in src/rdg/gemini.py is evaluated at *module import
time*: when RDG_PRIMARY=claude it checks claude_fallback.is_available() and
exit(1)s if the `claude` CLI is not resolvable, and it NEVER calls
genai.configure(). config.RDG_PRIMARY and config.api_key are likewise read at
import time. In-process monkeypatch+importlib.reload of that import-time exit is
fragile, so this test spawns the REAL CLI entrypoint (src/rdg/rdg_cli.py) in a
child process with a fully controlled environment, over a minimal `.rdg`
fixture that exercises exactly one GEMINIPROMPTFILE formula — the formula token
that routes through gemini.memoized_gemini_call → claude.call_claude when
RDG_PRIMARY=claude.

Environment isolation (premortem F3 — env / dotenv leak):
  - The child is launched with a CLEAN env dict (env=...), NOT the parent's, so
    a GEMINI_API_KEY that happens to be set in the agent shell cannot leak in.
  - config.py calls load_dotenv() at import, which searches UPWARD from the
    process cwd. The child's cwd is the pytest tmp_path (outside the repo), so
    the repo's own `.env` (which contains a placeholder GEMINI_API_KEY) is NOT
    discovered. We additionally point HOME at the tmp dir to avoid any
    user-level dotenv.
  - RDG_PRIMARY=claude and GEMINI_API_KEY is simply absent from the child env.

Fake LLM (premortem F2 — real API / real CLI call):
  - A tiny shell stub is written to the tmp dir, chmod +x, that ignores stdin
    and prints a DETERMINISTIC sentinel (RDG_FAKE_CLAUDE_OK_<uuid>), exit 0.
  - CLAUDE_CLI_PATH points DIRECTLY at the stub (shutil.which resolves an
    absolute path that exists+is executable), so even though a real `claude`
    binary exists on the agent's PATH, it is never reached. The child env's PATH
    is also a minimal /usr/bin:/bin without the user's ~/.local/bin.

Why green proves genai was NOT used (premortem F5 — import-time genai init,
assertion (b)): the Gemini branch of gemini.py requires either RDG_PRIMARY!=claude
OR, in its api_key branch, a non-empty GEMINI_API_KEY — and with no key it
exit(1)s ("GEMINI_API_KEY environment variable not set"). A child that runs
green to completion AND emits the fake-claude sentinel into the output file is
therefore *impossible* via the Gemini path; it can only have happened via the
claude branch (genai.configure is never called there). We additionally assert
the import-time "Gemini API configured successfully." log line is ABSENT and the
claude-primary log line is PRESENT.

Negative control against false-green (premortem F1 — over-mock / false green):
A test that stubbed call_claude directly in-process would still pass even if the
gemini→claude short-circuit in memoized_gemini_call were deleted. This test
drives the real entrypoint and asserts the deterministic sentinel reaches the
rendered output FILE, so deleting the short-circuit (which would route to the
Gemini path and exit(1) on the missing key) turns the test RED.

Fail-loud on missing prerequisite (assertion (c)): test_e2e_fails_loud_when_claude_absent
points CLAUDE_CLI_PATH at a non-existent binary and asserts the child exits
non-zero and writes NO output file — i.e. the test cannot silently pass when the
real prerequisite is absent.

Run (use the project venv — config.py imports python-dotenv, gemini.py imports
the genai SDK):
  cd rdg-notebook/reactive-docgen
  .venv/bin/python -m pytest tests/test_claude_primary_e2e.py -v
"""

from __future__ import annotations

import os
import subprocess
import sys
import uuid
from pathlib import Path

import pytest

# Repo layout: src/rdg/functions.py does `from ..llm.ollama import ollama_call`,
# so `rdg` must be imported as the `src.rdg` subpackage. The CLI entrypoint is
# therefore invoked as `python -m src.rdg.rdg_cli` with the reactive-docgen root
# on PYTHONPATH. (Mirrors tests/test_glob_exclude.py's `src.rdg` import basis.)
TESTS_DIR = Path(__file__).resolve().parent
REACTIVE_DOCGEN_DIR = TESTS_DIR.parent
SRC_DIR = REACTIVE_DOCGEN_DIR / "src"

CLI_MODULE = "src.rdg.rdg_cli"


# ─────────────────────────────────────────────────────────────────────────────
# Fixture builders
# ─────────────────────────────────────────────────────────────────────────────


def _write_fake_claude(work: Path, sentinel: str) -> Path:
    """Write a deterministic, zero-network `claude` stub and chmod +x it.

    The stub ignores stdin (the piped prompt) and prints the sentinel on stdout,
    exit 0 — exactly the surface src/rdg/claude.py:call_claude consumes
    (`--print` one-shot, returns result.stdout on returncode 0).
    """
    stub = work / "fake_claude.sh"
    stub.write_text(
        "#!/bin/sh\n"
        "# Hermetic claude stub: drain stdin, emit a deterministic sentinel.\n"
        "cat >/dev/null\n"
        f"printf '%s\\n' '{sentinel}'\n"
        "exit 0\n",
        encoding="utf-8",
    )
    stub.chmod(0o755)
    return stub


def _write_minimal_pipeline(work: Path) -> tuple[Path, Path]:
    """Write a minimal `.rdg` pipeline exercising exactly ONE GEMINIPROMPTFILE.

    Trimmed from sample.rdg's GEMINIPROMPTFILE line (samples/story-pirate.md):
      - one CREATEFILE produces the `$input` source, and
      - one GEMINIPROMPTFILE renders a template file with that input.
    GEMINIPROMPTFILE is the token that routes through gemini.memoized_gemini_call,
    which under RDG_PRIMARY=claude calls claude.call_claude.

    Returns (rdg_file, expected_output_file).
    """
    rdg_file = work / "pipeline.rdg"
    template_file = work / "tmpl.md"
    template_file.write_text("Process this: $input", encoding="utf-8")
    rdg_file.write_text(
        'input.md=CREATEFILE(content="hello pipeline")\n'
        'out.md=GEMINIPROMPTFILE(template_file="tmpl.md", input="input.md")\n',
        encoding="utf-8",
    )
    return rdg_file, (work / "out.md")


def _child_env(work: Path, claude_cli_path: str) -> dict[str, str]:
    """Build a CLEAN child environment.

    - GEMINI_API_KEY is INTENTIONALLY ABSENT (premortem F3): we do NOT inherit
      os.environ, so a key set in the agent shell cannot leak in.
    - RDG_PRIMARY=claude routes everything to the CLI.
    - CLAUDE_CLI_PATH points directly at the resolvable (or non-existent) stub.
    - PATH is minimal and excludes the user's ~/.local/bin, so the REAL `claude`
      is unreachable even by name (premortem F2).
    - HOME + cwd are the tmp dir so load_dotenv() cannot discover the repo `.env`
      (which carries a placeholder GEMINI_API_KEY) (premortem F3).
    """
    return {
        "PATH": "/usr/bin:/bin",
        "HOME": str(work),
        "PYTHONPATH": str(REACTIVE_DOCGEN_DIR),
        "RDG_PRIMARY": "claude",
        "CLAUDE_CLI_PATH": claude_cli_path,
        # Deterministic, no throttle surprises. (THROTTLE_SECONDS lives in config
        # but is not consulted on the claude path; included for hygiene only.)
        "PYTHONDONTWRITEBYTECODE": "1",
    }


def _run_pipeline(work: Path, env: dict[str, str]) -> subprocess.CompletedProcess:
    """Spawn `python -m src.rdg.rdg_cli <fixture>` with cwd=work, clean env."""
    rdg_file, _ = _write_minimal_pipeline(work)
    return subprocess.run(
        [sys.executable, "-m", CLI_MODULE, str(rdg_file)],
        cwd=str(work),
        env=env,
        capture_output=True,
        text=True,
        timeout=120,
    )


# ─────────────────────────────────────────────────────────────────────────────
# (a) Positive e2e + (b) no-genai: the claude path executes end-to-end and the
#     run is green with GEMINI_API_KEY UNSET (impossible via the Gemini path).
# ─────────────────────────────────────────────────────────────────────────────


def test_e2e_claude_primary_renders_fake_sentinel(tmp_path: Path) -> None:
    """ASSERTIONS (a) positive e2e + (b) no-genai.

    Drives the REAL CLI entrypoint over a one-formula GEMINIPROMPTFILE pipeline
    with RDG_PRIMARY=claude, GEMINI_API_KEY UNSET, and a deterministic fake
    `claude`. Asserts the fake sentinel reaches the rendered output FILE (a:
    proves the claude path ran end-to-end — not a stubbed call_claude) and that
    no Gemini SDK configuration occurred (b: green-without-key is impossible via
    the Gemini branch, which exit(1)s without a key; we also assert the log
    lines).
    """
    work = tmp_path
    sentinel = f"RDG_FAKE_CLAUDE_OK_{uuid.uuid4().hex}"
    stub = _write_fake_claude(work, sentinel)
    env = _child_env(work, str(stub))

    # Hard guard: the child env MUST NOT carry a Gemini key, regardless of the
    # agent shell. (Premortem F3 — env leak.)
    assert "GEMINI_API_KEY" not in env

    result = _run_pipeline(work, env)

    # (a) The run completed green …
    assert result.returncode == 0, (
        f"pipeline exited {result.returncode} with GEMINI_API_KEY unset + "
        f"RDG_PRIMARY=claude.\nstdout:\n{result.stdout}\nstderr:\n{result.stderr}"
    )
    out_file = work / "out.md"
    assert out_file.is_file(), "GEMINIPROMPTFILE produced no output file"
    out_text = out_file.read_text(encoding="utf-8")
    # … and the DETERMINISTIC fake-claude sentinel is in the rendered output.
    # This is the negative control against false-green (premortem F1): a test
    # that stubbed call_claude directly would pass even if the gemini→claude
    # short-circuit were deleted; this one would not (the Gemini path exit(1)s
    # on the missing key).
    assert sentinel in out_text, (
        "fake-claude sentinel missing from output — the RDG_PRIMARY=claude "
        f"short-circuit did not execute end-to-end.\nout.md:\n{out_text}\n"
        f"stderr:\n{result.stderr}"
    )

    # (b) No genai SDK call: green-without-key already proves it (the Gemini
    # branch requires a key, else exit(1)). Corroborate via the import-time logs.
    assert "RDG_PRIMARY=claude" in result.stderr, (
        "expected the claude-primary import log line; got:\n" + result.stderr
    )
    assert "Gemini API configured successfully." not in result.stderr, (
        "REGRESSION: Gemini SDK was configured — the claude-primary branch "
        "must skip genai.configure() entirely.\nstderr:\n" + result.stderr
    )
    assert "GEMINI_API_KEY environment variable not set" not in result.stderr, (
        "the Gemini path was taken (and failed for lack of a key) instead of "
        "the claude path — the short-circuit is broken.\nstderr:\n" + result.stderr
    )


def test_e2e_runs_with_gemini_key_unset(tmp_path: Path) -> None:
    """ASSERTION (b), explicit: prove GEMINI_API_KEY is genuinely absent from the
    child AND the run is still green.

    Because the Gemini branch exit(1)s when no key is present, a green run with
    the key provably unset is itself strong evidence the Gemini SDK path was not
    taken. This test isolates that claim from the sentinel assertion above.
    """
    work = tmp_path
    sentinel = f"RDG_FAKE_CLAUDE_OK_{uuid.uuid4().hex}"
    stub = _write_fake_claude(work, sentinel)
    env = _child_env(work, str(stub))
    assert "GEMINI_API_KEY" not in env

    result = _run_pipeline(work, env)
    assert result.returncode == 0, (
        "pipeline must run green with GEMINI_API_KEY unset under "
        f"RDG_PRIMARY=claude.\nstderr:\n{result.stderr}"
    )
    # Confirm the engine itself observed an unset key by the absence of the
    # Gemini-success log AND of the missing-key fatal log (claude branch is taken
    # before either could fire).
    assert "Gemini API configured successfully." not in result.stderr


# ─────────────────────────────────────────────────────────────────────────────
# (c) Fail-loud on missing prerequisite: claude CLI absent → non-zero exit, no
#     output file. The test cannot silently pass when the prereq is missing.
# ─────────────────────────────────────────────────────────────────────────────


def test_e2e_fails_loud_when_claude_absent(tmp_path: Path) -> None:
    """ASSERTION (c) + premortem F1 negative control.

    Wire EVERYTHING as in the positive test EXCEPT the fake claude stub: point
    CLAUDE_CLI_PATH at a non-existent binary and keep PATH free of any `claude`.
    src/rdg/gemini.py's import-time claude-primary check then exit(1)s, the CLI
    process exits non-zero, and NO output file is written. This guarantees the
    suite is not silently green when the real prerequisite (a resolvable claude)
    is genuinely absent — i.e. the stub is load-bearing, not decorative.
    """
    work = tmp_path
    # A path that does not resolve via shutil.which (does not exist).
    missing = work / "definitely_not_claude_does_not_exist"
    assert not missing.exists()
    env = _child_env(work, str(missing))
    assert "GEMINI_API_KEY" not in env

    result = _run_pipeline(work, env)

    assert result.returncode != 0, (
        "RDG_PRIMARY=claude with NO resolvable claude CLI must FAIL LOUD "
        f"(non-zero exit), not silently succeed.\nstdout:\n{result.stdout}\n"
        f"stderr:\n{result.stderr}"
    )
    # The import-time guard names the prerequisite.
    assert "requires the `claude` CLI" in result.stderr, (
        "expected the claude-prerequisite fatal log; got:\n" + result.stderr
    )
    # No phantom output: the formula never ran.
    assert not (work / "out.md").exists(), (
        "no output file may be produced when the claude prerequisite is absent"
    )


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-v"]))
