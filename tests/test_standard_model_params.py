#!/usr/bin/env python3
"""`model=` / `effort=` — the engine's standard parameters for model formulas.

Founder 2026-08-16: *"for all of our rdg formulas though, setting a model and effort should be
standard if an LLM is involved… we can just make them different parameters, that way model
switching is simple."*

The contract under test:

  PASS-THROUGH   a step's `model=` / `effort=` reach the provider invocation, from .rdg text to
                 process argv, on the serial runner and the RDG_JOBS wave runner alike.
  NON-LEAKAGE    they never reach template data. Every model formula funnels its remaining
                 arguments into the renderer, so the parser POPS these two first — otherwise
                 `model="opus"` becomes a `{{model}}` value and gets path-resolved as a file.
  FAIL-LOUD      an effort outside the ladder is refused at the line the author wrote, before any
                 call. Both providers ACCEPT a bad level and keep going (the Claude CLI warns on
                 stderr and runs at its default — measured 2026-07-30; Gemini simply receives no
                 thinking config), so the silent version of this exits 0 having used an effort
                 nobody asked for.
  MEANINGFUL     a formula that ships here and does not call a model REFUSES the two names, so
                 they cannot decay into "arguments some formulas happen to ignore". Externally
                 loaded formulas are exempt unless they declare themselves — the engine cannot
                 know another module's vocabulary, and the consumer repo's CLAUDECODE takes
                 `model=`/`effort=` today.
  OBSERVABILITY  one primitive event per real provider call, on the same RDG_EVENTS opt-in as the
                 step events, field-for-field the CLAUDECODE twin in the consumer repo.

Hermetic (the idiom of tests/test_claude_primary_e2e.py — NO network, NO API key, NO real LLM):
the child runs with RDG_PRIMARY=claude, a clean env with GEMINI_API_KEY absent, and a `claude`
stub that echoes its own ARGV and its STDIN. The stub's output IS the observation — what the
engine passed to the provider, and what it did not.

Each run gets a fresh RDG_CACHE_DIR. Without that, a second run of an identical prompt is served
from the response cache, makes no call, emits no primitive event, and the test would be asserting
on the cache rather than on the engine.

Run (use the project venv):
  cd rdg-notebook/reactive-docgen
  .venv/bin/python -m pytest tests/test_standard_model_params.py -v
"""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
import uuid
from pathlib import Path

import pytest

TESTS_DIR = Path(__file__).resolve().parent
REPO = TESTS_DIR.parent
CLI_MODULE = "src.rdg.rdg_cli"

sys.path.insert(0, str(REPO))

# The stub is the measurement instrument: ARGV shows what was dispatched, STDIN shows the prompt
# that was actually sent. Both halves are needed — pass-through is proven by one, non-leakage by
# the other, and a single run yields both.
ECHO_STUB = """#!/bin/sh
printf 'ARGV: %s\\n' "$*"
printf 'STDIN: '
cat
"""


def _write_stub(work: Path, body: str = ECHO_STUB) -> Path:
    stub = work / "fake_claude.sh"
    stub.write_text(body, encoding="utf-8")
    stub.chmod(0o755)
    return stub


def _child_env(work: Path, cli: Path, extra: dict[str, str] | None = None) -> dict[str, str]:
    """A CLEAN child environment: no inherited GEMINI_API_KEY, no reachable real `claude`.

    HOME and cwd are the tmp dir so config.py's load_dotenv() cannot discover the repo's own
    `.env`, and PATH excludes the user's ~/.local/bin so the stub is the only CLI in reach.
    """
    env = {
        "PATH": "/usr/bin:/bin",
        "HOME": str(work),
        "PYTHONPATH": str(REPO),
        "PYTHONDONTWRITEBYTECODE": "1",
        "RDG_PRIMARY": "claude",
        "CLAUDE_CLI_PATH": str(cli),
        "RDG_CACHE_DIR": str(work / "cache"),
    }
    if extra:
        env.update(extra)
    return env


def _run(tmp_path: Path, name: str, body: str, *, env_extra=None, stub_body=ECHO_STUB, files=None):
    """Run one `.rdg` in its own working directory. Returns (CompletedProcess, work_dir)."""
    work = tmp_path / name
    work.mkdir()
    for filename, content in (files or {"in.md": "PROMPT_BODY"}).items():
        (work / filename).write_text(content, encoding="utf-8")
    rdg = work / "t.rdg"
    rdg.write_text(body, encoding="utf-8")
    stub = _write_stub(work, stub_body)
    proc = subprocess.run(
        [sys.executable, "-m", CLI_MODULE, str(rdg)],
        cwd=str(work),
        env=_child_env(work, stub, env_extra),
        capture_output=True,
        text=True,
        timeout=120,
    )
    return proc, work


def _argv(work: Path, dest: str = "out.md") -> str:
    """The ARGV line the stub echoed — i.e. what the engine dispatched."""
    text = (work / dest).read_text(encoding="utf-8")
    assert text.startswith("ARGV: "), f"the CLI was never invoked; {dest} holds:\n{text}"
    return text.split("\n", 1)[0]


def _stdin(work: Path, dest: str = "out.md") -> str:
    """The prompt the engine actually sent."""
    text = (work / dest).read_text(encoding="utf-8")
    marker = "STDIN: "
    assert marker in text, f"no prompt was piped; {dest} holds:\n{text}"
    return text.split(marker, 1)[1]


def _events(stderr: str) -> list[dict]:
    out = []
    for line in stderr.splitlines():
        line = line.strip()
        if not line.startswith("{"):
            continue
        try:
            obj = json.loads(line)
        except json.JSONDecodeError:
            continue
        if "ev" in obj:
            out.append(obj)
    return out


def _primitives(stderr: str) -> list[dict]:
    return [e for e in _events(stderr) if e["ev"] == "primitive"]


# ─────────────────────────────────────────────────────────────────────────────
# Pass-through + non-leakage
# ─────────────────────────────────────────────────────────────────────────────


def test_step_params_reach_the_provider_invocation(tmp_path: Path) -> None:
    """The whole point: what the .rdg line says is what the provider is asked for."""
    proc, work = _run(
        tmp_path, "passthrough",
        'out.md=GEMINIPROMPT(template="Answer: {{x}}", x=in.md, model="opus", effort="max")\n',
    )
    assert proc.returncode == 0, proc.stderr
    argv = _argv(work)
    assert "--model opus" in argv, argv
    assert "--effort max" in argv, argv


def test_standard_params_never_become_template_data(tmp_path: Path) -> None:
    """The regression this design exists to prevent, asserted where it is VISIBLE.

    Model formulas turn every remaining argument into template data and path-resolve it, so a
    `model=` that survived the argument bag would be available to the renderer — and would ride
    into the prompt as content. Because the parser pops it first, a template that references
    `{{model}}` must fail as an unresolved placeholder rather than quietly rendering "opus".
    That failure IS the proof; a prompt that merely happens not to mention the model would pass
    either way.
    """
    proc, work = _run(
        tmp_path, "noleak",
        'out.md=GEMINIPROMPT(template="Answer: {{x}} {{model}}", x=in.md, model="opus")\n',
    )
    assert proc.returncode != 0, proc.stdout + proc.stderr
    assert "Template placeholder not found" in proc.stderr, proc.stderr
    assert "model" in proc.stderr, proc.stderr
    report = (work / "out.md").read_text(encoding="utf-8")
    assert report.startswith("## ERROR"), report
    assert "ARGV:" not in report, "the prompt never rendered, so nothing should have been called"
    # The failure explains ITSELF: this is the shape two live steps in the consumer repo have
    # (.rdg/asset-3-holdings.rdg:39,51 pass `model=<path>` and reference {{model}}), and a bare
    # "placeholder not found" would point nowhere near the cause.
    assert "STANDARD PARAMETER" in report, f"the collision hint is missing:\n{report}"
    assert "domain_model=" in report, f"the hint must name the fix:\n{report}"


def test_the_prompt_carries_content_and_nothing_else(tmp_path: Path) -> None:
    """Companion to the above from the other side: on the working path, the rendered prompt is
    the content — the dispatch parameters are not in it."""
    marker = f"PROMPT_BODY_{uuid.uuid4().hex}"
    proc, work = _run(
        tmp_path, "promptbody",
        'out.md=GEMINIPROMPT(template="Answer: {{x}}", x=in.md, model="opus", effort="max")\n',
        files={"in.md": marker},
    )
    assert proc.returncode == 0, proc.stderr
    prompt = _stdin(work)
    assert marker in prompt, prompt
    assert "opus" not in prompt, f"model= leaked into the prompt:\n{prompt}"


def test_absent_effort_inherits_the_provider_default(tmp_path: Path) -> None:
    """Unset must not become a level this engine picked: the flag is omitted entirely."""
    proc, work = _run(
        tmp_path, "noeffort",
        'out.md=GEMINIPROMPT(template="Answer: {{x}}", x=in.md, model="opus")\n',
    )
    assert proc.returncode == 0, proc.stderr
    argv = _argv(work)
    assert "--model opus" in argv, argv
    assert "--effort" not in argv, argv


def test_summarize_takes_the_same_two_parameters(tmp_path: Path) -> None:
    """SUMMARIZE is a model formula, so it carries the standard parameters like the rest —
    and its primitive event names SUMMARIZE, not the formula it used to delegate to."""
    proc, work = _run(
        tmp_path, "summarize",
        'out.md=SUMMARIZE(file=in.md, model="haiku", effort="low")\n',
        env_extra={"RDG_EVENTS": "jsonl"},
    )
    assert proc.returncode == 0, proc.stderr
    argv = _argv(work)
    assert "--model haiku" in argv, argv
    assert "--effort low" in argv, argv
    primitives = _primitives(proc.stderr)
    assert [p["formula"] for p in primitives] == ["SUMMARIZE"], proc.stderr


def test_wave_runner_applies_the_same_contract(tmp_path: Path) -> None:
    """RDG_JOBS shares _run_step, so the parameters cannot be a serial-only feature."""
    proc, work = _run(
        tmp_path, "waves",
        'out.md=GEMINIPROMPT(template="A: {{x}}", x=in.md, model="opus", effort="high")\n'
        'out2.md=GEMINIPROMPT(template="B: {{x}}", x=in.md, model="haiku", effort="low")\n',
        env_extra={"RDG_JOBS": "2"},
    )
    assert proc.returncode == 0, proc.stderr
    assert "--model opus" in _argv(work, "out.md")
    assert "--effort high" in _argv(work, "out.md")
    assert "--model haiku" in _argv(work, "out2.md")
    assert "--effort low" in _argv(work, "out2.md")


# ─────────────────────────────────────────────────────────────────────────────
# Fail-loud: a level nobody defined, and a formula that does not call a model
# ─────────────────────────────────────────────────────────────────────────────


def test_unknown_effort_is_refused_before_any_call(tmp_path: Path) -> None:
    """'hgih' is the transposition measured against the real CLI: it warns and runs at DEFAULT
    effort, exit 0. The engine must refuse it first, and must not have called anything."""
    proc, work = _run(
        tmp_path, "badeffort",
        'out.md=GEMINIPROMPT(template="Answer: {{x}}", x=in.md, effort="hgih")\n',
    )
    assert proc.returncode != 0, proc.stdout + proc.stderr
    assert "hgih" in proc.stderr, proc.stderr
    assert "low | medium | high | xhigh | max" in proc.stderr, proc.stderr
    report = (work / "out.md").read_text(encoding="utf-8")
    assert report.startswith("## ERROR"), report
    assert "ARGV:" not in report, "a refused effort must not reach the provider"


def test_non_model_formula_refuses_the_standard_params(tmp_path: Path) -> None:
    """CREATEFILE absorbs unknown arguments as template data, which is exactly why the refusal is
    at the parser: `model=` there would silently become content."""
    proc, work = _run(
        tmp_path, "notmodel", 'out.md=CREATEFILE(content="hello", model="opus")\n',
    )
    assert proc.returncode != 0, proc.stdout + proc.stderr
    assert "CREATEFILE" in proc.stderr, proc.stderr
    assert "model" in proc.stderr, proc.stderr
    report = (work / "out.md").read_text(encoding="utf-8")
    assert report.startswith("## ERROR"), report


def test_the_same_formula_without_the_params_still_works(tmp_path: Path) -> None:
    """Control for the refusal above: it is the parameter that is refused, not the formula."""
    proc, work = _run(tmp_path, "control", 'out.md=CREATEFILE(content="hello")\n')
    assert proc.returncode == 0, proc.stderr
    assert (work / "out.md").read_text(encoding="utf-8") == "hello"


# ─────────────────────────────────────────────────────────────────────────────
# Primitive observability — one line per real call, on the RDG_EVENTS opt-in
# ─────────────────────────────────────────────────────────────────────────────


def test_primitive_event_names_what_actually_ran(tmp_path: Path) -> None:
    body = 'out.md=GEMINIPROMPT(template="Answer: {{x}}", x=in.md, model="opus", effort="max")\n'
    proc, work = _run(tmp_path, "primitive", body, env_extra={"RDG_EVENTS": "jsonl"})
    assert proc.returncode == 0, proc.stderr

    primitives = _primitives(proc.stderr)
    assert len(primitives) == 1, f"expected exactly one invocation:\n{proc.stderr}"
    event = primitives[0]
    assert event["ev"] == "primitive", "one envelope key for every event kind"
    assert event["phase"] == "attempt", "stated, so a completion event needs no schema break"
    assert event["formula"] == "GEMINIPROMPT", "the .rdg formula, not the backend that ran it"
    assert event["model"] == "opus"
    assert event["effort"] == "max"
    assert event["backend"] == "claude"
    assert isinstance(event["timeout_s"], int)
    assert "ts" in event
    # The negative contract: dispatch facts only.
    assert "workdir" not in event, "no filesystem paths in an open-source tool's events"
    assert "PROMPT_BODY" not in json.dumps(event), "no prompt text in events"
    # Step events are a separate kind on the same stream; both must survive.
    assert [e["ev"] for e in _events(proc.stderr)].count("step_end") == 1, proc.stderr


def test_primitive_event_is_silent_without_rdg_events(tmp_path: Path) -> None:
    """Engine-side logging is opt-in (founder 2026-08-16): a consumer that never asked for a
    machine stream gets a clean stderr — while the run itself is unchanged."""
    body = 'out.md=GEMINIPROMPT(template="Answer: {{x}}", x=in.md, model="opus", effort="max")\n'
    proc, work = _run(tmp_path, "quiet", body)
    assert proc.returncode == 0, proc.stderr
    assert _primitives(proc.stderr) == [], proc.stderr
    # …and the call still happened with the requested parameters.
    assert "--model opus" in _argv(work)


def test_no_primitive_event_on_a_cache_hit(tmp_path: Path) -> None:
    """A line for a call that did not happen is a phantom. The second run is served from the
    response cache, so it must report no invocation — and must still produce the artifact."""
    body = 'out.md=GEMINIPROMPT(template="Answer: {{x}}", x=in.md, model="opus")\n'
    work = tmp_path / "cachehit"
    work.mkdir()
    (work / "in.md").write_text("PROMPT_BODY", encoding="utf-8")
    rdg = work / "t.rdg"
    rdg.write_text(body, encoding="utf-8")
    stub = _write_stub(work)
    env = _child_env(work, stub, {"RDG_EVENTS": "jsonl"})

    first = subprocess.run([sys.executable, "-m", CLI_MODULE, str(rdg)], cwd=str(work), env=env,
                           capture_output=True, text=True, timeout=120)
    second = subprocess.run([sys.executable, "-m", CLI_MODULE, str(rdg)], cwd=str(work), env=env,
                            capture_output=True, text=True, timeout=120)

    assert first.returncode == 0 and second.returncode == 0, first.stderr + second.stderr
    assert len(_primitives(first.stderr)) == 1, first.stderr
    assert _primitives(second.stderr) == [], second.stderr
    assert "ARGV:" in (work / "out.md").read_text(encoding="utf-8")


# ─────────────────────────────────────────────────────────────────────────────
# Non-zero exit fidelity: the cause is on STDOUT under --output-format json
# ─────────────────────────────────────────────────────────────────────────────


FAILING_STUB = """#!/bin/sh
cat >/dev/null
printf '%s\\n' '{"type":"result","is_error":true,"result":"CAUSE_ON_STDOUT"}'
exit 1
"""


def test_nonzero_exit_reports_the_stdout_tail(tmp_path: Path) -> None:
    """Reproduces the live failure EXACTLY: non-zero exit, EMPTY stderr, error JSON on STDOUT.

    `claude --print --output-format json` puts its error payload on stdout, so a stderr-only tail
    reported every real failure as "exit 1:" with nothing after the colon — observed twice on
    rtb-runner/graph/migration-report.rdg. The cause was on stdout the whole time and the report
    dropped it, leaving an operator with a failure that names no reason.

    Unconditional, unlike the events: error fidelity is not logging. A report that omits the cause
    is wrong even for a consumer that wants no machine stream.
    """
    proc, work = _run(
        tmp_path, "stdouttail",
        'out.md=GEMINIPROMPT(template="Answer: {{x}}", x=in.md)\n',
        stub_body=FAILING_STUB,
        # No RDG_EVENTS: the fix must hold on the quiet path too.
    )
    report = (work / "out.md").read_text(encoding="utf-8")
    assert "RDG-ENGINE-ERROR" in report, report
    assert "ClaudeCliNonZeroExit" in report, report
    assert "CAUSE_ON_STDOUT" in report, f"the failure cause was dropped:\n{report}"
    # The precise shape of the old bug: a sentinel that ends at the colon.
    assert "exit 1: |" not in report and not report.rstrip().endswith("exit 1:"), (
        "the report degenerated to a bare exit code with no cause:\n" + report
    )


# ─────────────────────────────────────────────────────────────────────────────
# External formulas: opt in by declaring, unaffected otherwise
# ─────────────────────────────────────────────────────────────────────────────


DECLARED_MODULE = '''
"""An external formula that declares itself model-class."""

def call_model(rdg_file, **kwargs):
    return f"model={kwargs.get('model')} effort={kwargs.get('effort')}"

FORMULAS = {"EXTMODEL": call_model}
MODEL_FORMULAS = {"EXTMODEL"}
'''

UNDECLARED_MODULE = '''
"""An external formula that has NOT declared itself — the shape shipped today."""

def call_model(rdg_file, **kwargs):
    return f"model={kwargs.get('model')} effort={kwargs.get('effort')}"

FORMULAS = {"EXTPLAIN": call_model}
'''


def _with_formulas(tmp_path: Path, name: str, module_src: str, body: str, module_name="ext.py"):
    work = tmp_path / name
    work.mkdir()
    formulas = work / "formulas"
    formulas.mkdir()
    (formulas / module_name).write_text(module_src, encoding="utf-8")
    (work / "in.md").write_text("PROMPT_BODY", encoding="utf-8")
    rdg = work / "t.rdg"
    rdg.write_text(body, encoding="utf-8")
    stub = _write_stub(work)
    env = _child_env(work, stub, {"RDG_FORMULA_PATH": str(formulas)})
    proc = subprocess.run([sys.executable, "-m", CLI_MODULE, str(rdg)], cwd=str(work), env=env,
                          capture_output=True, text=True, timeout=120)
    return proc, work


def test_declared_external_formula_joins_the_contract(tmp_path: Path) -> None:
    proc, work = _with_formulas(
        tmp_path, "extdeclared", DECLARED_MODULE,
        'out.md=EXTMODEL(model="opus", effort="high")\n',
    )
    assert proc.returncode == 0, proc.stderr
    assert (work / "out.md").read_text(encoding="utf-8") == "model=opus effort=high"


def test_declared_external_formula_gets_the_effort_validation(tmp_path: Path) -> None:
    """Declaring is what buys the typo protection — the engine now knows the vocabulary."""
    proc, work = _with_formulas(
        tmp_path, "extbadeffort", DECLARED_MODULE, 'out.md=EXTMODEL(effort="hgih")\n',
    )
    assert proc.returncode != 0, proc.stdout + proc.stderr
    assert "hgih" in proc.stderr, proc.stderr


def test_undeclared_external_formula_is_passed_through_untouched(tmp_path: Path) -> None:
    """The compatibility guarantee, pinned deliberately: the consumer repo's CLAUDECODE takes
    `model=`/`effort=` and pops them itself. The engine must not refuse an external call it has
    no vocabulary for — refusing on a guess would break every pipeline using it."""
    proc, work = _with_formulas(
        tmp_path, "extplain", UNDECLARED_MODULE,
        'out.md=EXTPLAIN(model="opus", effort="whatever-it-defines")\n',
    )
    assert proc.returncode == 0, proc.stderr
    assert (work / "out.md").read_text(encoding="utf-8") == \
        "model=opus effort=whatever-it-defines"


def test_declaring_a_formula_it_does_not_own_fails_loud(tmp_path: Path) -> None:
    proc, _ = _with_formulas(
        tmp_path, "extbogus",
        DECLARED_MODULE.replace('MODEL_FORMULAS = {"EXTMODEL"}',
                                'MODEL_FORMULAS = {"SOMETHING_ELSE"}'),
        'out.md=EXTMODEL(model="opus")\n',
    )
    assert proc.returncode != 0
    assert "MODEL_FORMULAS" in proc.stderr, proc.stderr


# ─────────────────────────────────────────────────────────────────────────────
# In-process units: cache identity and the effort→thinking-level mapping
# ─────────────────────────────────────────────────────────────────────────────


def test_default_call_keeps_the_historical_cache_key(monkeypatch) -> None:
    """Backward compatibility is load-bearing: hundreds of cached responses on disk are addressed
    by md5(prompt), and switch.py re-derives that md5 by hand for its byte-equality fast path."""
    from src.rdg import config, gemini

    monkeypatch.setattr(config, "GEMINI_MODEL", config.GEMINI_MODEL_DEFAULT)
    monkeypatch.setattr(config, "GEMINI_EFFORT", None)
    prompt = "Summarize the following text:\n\nhello"
    assert gemini.get_cache_key(prompt) == hashlib.md5(prompt.encode()).hexdigest()
    assert gemini.get_cache_key(prompt, None, None) == gemini.get_cache_key(prompt)
    # Naming the default explicitly is the SAME call, so it must not fork the namespace.
    assert gemini.get_cache_key(prompt, config.GEMINI_MODEL_DEFAULT) == gemini.get_cache_key(prompt)


def test_a_different_model_or_effort_gets_its_own_cache_namespace(monkeypatch) -> None:
    """Serving one model's cached answer as another model's answer would make `model=` a claim
    rather than a fact."""
    from src.rdg import config, gemini

    monkeypatch.setattr(config, "GEMINI_MODEL", config.GEMINI_MODEL_DEFAULT)
    monkeypatch.setattr(config, "GEMINI_EFFORT", None)
    prompt = "same prompt, different call"
    base = gemini.get_cache_key(prompt)
    assert gemini.get_cache_key(prompt, "gemini-3-pro-preview") != base
    assert gemini.get_cache_key(prompt, None, "max") != base
    assert gemini.get_cache_key(prompt, "gemini-3-pro-preview", "max") != \
        gemini.get_cache_key(prompt, "gemini-3-pro-preview", "low")


def test_effort_maps_onto_the_gemini_thinking_ladder() -> None:
    """Name-preserving and saturating: `high` must mean HIGH, and the two rungs above Gemini's
    ceiling must not silently mean something lower."""
    from google.genai import types

    from src.rdg import config, gemini

    assert set(gemini.EFFORT_THINKING_LEVEL) == set(config.EFFORT_LEVELS), \
        "every ladder level must map, or an accepted effort would raise at call time"
    assert gemini.EFFORT_THINKING_LEVEL["low"] == types.ThinkingLevel.LOW
    assert gemini.EFFORT_THINKING_LEVEL["medium"] == types.ThinkingLevel.MEDIUM
    assert gemini.EFFORT_THINKING_LEVEL["high"] == types.ThinkingLevel.HIGH
    assert gemini.EFFORT_THINKING_LEVEL["xhigh"] == types.ThinkingLevel.HIGH
    assert gemini.EFFORT_THINKING_LEVEL["max"] == types.ThinkingLevel.HIGH


def test_absent_effort_sends_no_thinking_config() -> None:
    """"The step did not ask" must mean the provider's own default, not a level we chose."""
    from google.genai import types

    from src.rdg import gemini

    assert gemini.config_for(None) is gemini.generation_config
    assert gemini.generation_config.thinking_config is None, "the base config must stay untouched"
    configured = gemini.config_for("high")
    assert configured.thinking_config == types.ThinkingConfig(
        thinking_level=types.ThinkingLevel.HIGH
    )
    assert configured.temperature == gemini.generation_config.temperature, \
        "a per-call copy must not drop the rest of the configuration"


def test_build_argv_takes_the_step_parameters() -> None:
    """The Claude backend is a model backend and takes the same two parameters; None means this
    run's configured default, which is what preserves the pre-existing env-only behavior."""
    from src.rdg import claude, config

    assert claude.build_argv("/usr/bin/claude", "opus", "max") == [
        "/usr/bin/claude", "--print", "--model", "opus", "--effort", "max",
    ]
    default = claude.build_argv("/usr/bin/claude")
    assert default[:4] == ["/usr/bin/claude", "--print", "--model", config.CLAUDE_CLI_MODEL]


def test_the_resolvers_themselves_refuse_a_bad_level() -> None:
    """The parser is not the only door. Validation lives in the resolvers — the last point common
    to every path into a provider — so a per-step effort cannot reach an argv or a thinking config
    unchecked no matter who called. Without this, `build_argv(cli, None, "hgih")` builds
    `--effort hgih`, the CLI warns and runs at its default, and the run is green at the wrong
    level: precisely the regression tests/test_claude_effort_flag.py exists to prevent, reachable
    again through the new parameter.
    """
    from src.rdg import claude, config

    with pytest.raises(ValueError, match="hgih"):
        config.resolve_claude_params(None, "hgih")
    with pytest.raises(ValueError, match="hgih"):
        config.resolve_gemini_params(None, "hgih")
    with pytest.raises(ValueError):
        claude.build_argv("/usr/bin/claude", "opus", "hgih")
    # The empty string is a mistake, not a request for the default.
    with pytest.raises(ValueError):
        config.resolve_claude_params(None, "")


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-v"]))
