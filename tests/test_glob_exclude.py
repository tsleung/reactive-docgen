#!/usr/bin/env python3
"""
RDG Engine GLOB/FILES exclude-support Regression Test.

WorkGraph: wo-task-rdg-engine-glob-exclude-support (P2/I3)

Problem (pre-fix): `glob_to_markdown` (GLOBTOMARKDOWN) and
`create_markdown_from_files` (FILESTOMARKDOWN) read ONLY their required kwarg
(`pattern` / `files`) and SILENTLY DROPPED everything else. 26 live `.rdg`
usages pass `exclude="**/*.spec.ts,**/*.vitest.ts,**/__tests__/**"` assuming
tests are filtered — they were NOT. Audit partitions bloated 150KB -> 2.98MB
with test-file content because the documented-intent `exclude=` kwarg was a
no-op.

Required behavior (this suite's contract):
  - `exclude` is an optional comma-separated string of glob patterns.
  - A file is excluded if it matches ANY pattern.
  - GLOBTOMARKDOWN matches against the rdg_dir-relative display path;
    FILESTOMARKDOWN matches against the `files=` entry as given.
  - `**/<dir>/**` and `**/*.ext` MUST cross directory separators correctly
    (fnmatch does not; we use PurePath.full_match / a guarded fallback).
  - Excluding nothing leaves every file present (no over-filter).
  - Unknown kwargs fail loud (raise RdgParserError) — the allowlists are
    verified zero-risk against every live a consumer repo usage.

This is a STRUCTURAL test — no network, no LLM, no credentials. It writes real
fixture files into a pytest tmp_path and inspects the emitted markdown.

Run (use the project venv — functions.py -> gemini.py imports the SDK/config):
  cd rdg-notebook/reactive-docgen
  .venv/bin/python -m pytest tests/test_glob_exclude.py -v
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

# functions.py uses BOTH `from rdg.gemini import ...` (absolute) and
# `from ..llm.ollama import ...` (package-relative beyond `rdg`). The relative
# import only resolves when `rdg` is imported as a subpackage of `src`, so we
# put the reactive-docgen root (the parent of `src`) on the path and import via
# the `src.rdg.functions` dotted path. This mirrors the real runtime, where the
# engine is invoked as part of the `src` package.
TESTS_DIR = Path(__file__).resolve().parent
REACTIVE_DOCGEN_DIR = TESTS_DIR.parent

if str(REACTIVE_DOCGEN_DIR) not in sys.path:
    sys.path.insert(0, str(REACTIVE_DOCGEN_DIR))

from src.rdg.functions import (  # noqa: E402
    RdgParserError,
    create_markdown_from_files,
    glob_to_markdown,
)


# ─────────────────────────────────────────────────────────────────────────────
# Fixture: a nested tree of files under a tmp "rdg dir", plus the rdg_file path
# the engine functions resolve everything relative to.
# ─────────────────────────────────────────────────────────────────────────────


def _write(base: Path, rel: str, content: str) -> None:
    full = base / rel
    full.parent.mkdir(parents=True, exist_ok=True)
    full.write_text(content, encoding="utf-8")


@pytest.fixture()
def tree(tmp_path: Path):
    """Create a project-like tree and return (rdg_file_path, base_dir).

    The engine uses `os.path.dirname(os.path.abspath(rdg_file))` as the base
    directory for both functions, so we place a dummy `pipeline.rdg` at the root
    and write source/test files around it.
    """
    base = tmp_path / "proj"
    base.mkdir()
    rdg_file = base / "pipeline.rdg"
    rdg_file.write_text("# dummy rdg\n", encoding="utf-8")

    # Production source files (should survive exclusion).
    _write(base, "src/foo.component.ts", "export const foo = 1;")
    _write(base, "src/nested/bar.component.ts", "export const bar = 2;")
    # Co-located spec at depth (the canonical bloat source).
    _write(base, "src/nested/bar.spec.ts", "describe('bar', () => {});")
    # A top-level spec (verifies **/*.spec.ts matches zero-dir depth too).
    _write(base, "src/baz.spec.ts", "describe('baz', () => {});")
    # A vitest file.
    _write(base, "src/qux.vitest.ts", "test('qux', () => {});")
    # A nested __tests__ directory (directory-exclude target).
    _write(base, "src/feature/__tests__/helper.ts", "export const h = 3;")
    _write(base, "src/feature/__tests__/another.ts", "export const a = 4;")

    return str(rdg_file), base


def _headings(markdown: str) -> set[str]:
    """Extract the `## <path>` headings the engine emits, for assertion."""
    return {
        line[len("## "):].strip()
        for line in markdown.splitlines()
        if line.startswith("## ")
    }


# ─────────────────────────────────────────────────────────────────────────────
# (a) exclude removes a .spec.ts; non-matching files pass through
# ─────────────────────────────────────────────────────────────────────────────


def test_glob_exclude_removes_spec_keeps_source(tree) -> None:
    rdg_file, _base = tree
    out = glob_to_markdown(
        rdg_file,
        pattern="src/nested/*.ts",
        exclude="**/*.spec.ts",
    )
    headings = _headings(out)
    # PREMORTEM #1 (path-basis mismatch): assert the spec is ACTUALLY gone.
    assert "src/nested/bar.spec.ts" not in headings, (
        "exclude='**/*.spec.ts' must drop the co-located spec; if present the "
        "exclude is matched against the wrong path basis (silent non-filter)."
    )
    # Non-matching source survives.
    assert "src/nested/bar.component.ts" in headings


def test_glob_without_exclude_includes_everything(tree) -> None:
    """Baseline: with NO exclude, the spec is present (proves the pattern would
    otherwise include it — the bug being fixed)."""
    rdg_file, _base = tree
    out = glob_to_markdown(rdg_file, pattern="src/nested/*.ts")
    headings = _headings(out)
    assert "src/nested/bar.spec.ts" in headings
    assert "src/nested/bar.component.ts" in headings


# ─────────────────────────────────────────────────────────────────────────────
# (b) **/__tests__/** directory-exclude removes a nested __tests__ file
# ─────────────────────────────────────────────────────────────────────────────


def test_glob_exclude_tests_directory(tree) -> None:
    rdg_file, _base = tree
    out = glob_to_markdown(
        rdg_file,
        pattern="src/**/*.ts",
        exclude="**/__tests__/**",
    )
    headings = _headings(out)
    # PREMORTEM #2 (** not honored by fnmatch): the directory-exclude must
    # remove BOTH files inside the nested __tests__ dir.
    assert "src/feature/__tests__/helper.ts" not in headings
    assert "src/feature/__tests__/another.ts" not in headings
    # Sources elsewhere survive.
    assert "src/foo.component.ts" in headings
    assert "src/nested/bar.component.ts" in headings


# ─────────────────────────────────────────────────────────────────────────────
# (c) Multiple comma-separated exclude patterns all apply
# ─────────────────────────────────────────────────────────────────────────────


def test_glob_multiple_exclude_patterns(tree) -> None:
    rdg_file, _base = tree
    out = glob_to_markdown(
        rdg_file,
        pattern="src/**/*.ts",
        exclude="**/*.spec.ts,**/*.vitest.ts,**/__tests__/**",
    )
    headings = _headings(out)
    # Every excluded category gone.
    assert "src/nested/bar.spec.ts" not in headings
    assert "src/baz.spec.ts" not in headings  # top-level spec (zero-dir **)
    assert "src/qux.vitest.ts" not in headings
    assert "src/feature/__tests__/helper.ts" not in headings
    assert "src/feature/__tests__/another.ts" not in headings
    # Production sources remain.
    assert "src/foo.component.ts" in headings
    assert "src/nested/bar.component.ts" in headings


# ─────────────────────────────────────────────────────────────────────────────
# (d) Exclude that matches NOTHING leaves all files present (no over-filter)
# ─────────────────────────────────────────────────────────────────────────────


def test_glob_exclude_matching_nothing_keeps_all(tree) -> None:
    rdg_file, _base = tree
    no_exclude = _headings(glob_to_markdown(rdg_file, pattern="src/**/*.ts"))
    with_inert_exclude = _headings(
        glob_to_markdown(
            rdg_file,
            pattern="src/**/*.ts",
            exclude="**/*.NOPE,**/does-not-exist/**",
        )
    )
    # PREMORTEM #5 (over-filter silent empty): an exclude that matches nothing
    # must NOT remove anything.
    assert with_inert_exclude == no_exclude
    assert len(with_inert_exclude) > 0


def test_glob_exclude_everything_reaches_no_match_branch(tree) -> None:
    """If exclusion empties the set, the existing 'No files matched' behavior
    must be reachable (not a crash)."""
    rdg_file, _base = tree
    out = glob_to_markdown(
        rdg_file,
        pattern="src/nested/bar.spec.ts",
        exclude="**/*.spec.ts",
    )
    assert "No files matched" in out
    assert _headings(out) == set()


# ─────────────────────────────────────────────────────────────────────────────
# (e) FILESTOMARKDOWN: exclude filters the explicit files= list too
# ─────────────────────────────────────────────────────────────────────────────


def test_files_to_markdown_exclude_filters_list(tree) -> None:
    rdg_file, _base = tree
    files = (
        "src/foo.component.ts,"
        "src/nested/bar.spec.ts,"
        "src/qux.vitest.ts,"
        "src/feature/__tests__/helper.ts"
    )
    out = create_markdown_from_files(
        rdg_file,
        files=files,
        exclude="**/*.spec.ts,**/*.vitest.ts,**/__tests__/**",
    )
    headings = _headings(out)
    assert "src/foo.component.ts" in headings
    assert "src/nested/bar.spec.ts" not in headings
    assert "src/qux.vitest.ts" not in headings
    assert "src/feature/__tests__/helper.ts" not in headings


def test_files_to_markdown_without_exclude_keeps_all(tree) -> None:
    rdg_file, _base = tree
    out = create_markdown_from_files(
        rdg_file,
        files="src/foo.component.ts,src/nested/bar.spec.ts",
    )
    headings = _headings(out)
    assert "src/foo.component.ts" in headings
    assert "src/nested/bar.spec.ts" in headings


# ─────────────────────────────────────────────────────────────────────────────
# (f) raise-on-unknown: genuinely-unknown kwarg raises; known kwargs do not.
#     (Enabled because the .rdg audit confirmed only {pattern,exclude} /
#      {files,exclude} appear in production — zero risk.)
# ─────────────────────────────────────────────────────────────────────────────


def test_glob_unknown_kwarg_raises(tree) -> None:
    rdg_file, _base = tree
    with pytest.raises(RdgParserError) as exc:
        glob_to_markdown(rdg_file, pattern="src/**/*.ts", exlcude="**/*.spec.ts")
    assert "Unknown parameter" in str(exc.value)
    assert "GLOBTOMARKDOWN" in str(exc.value)
    # The classic typo must be named so the author can fix it.
    assert "exlcude" in str(exc.value)


def test_files_unknown_kwarg_raises(tree) -> None:
    rdg_file, _base = tree
    with pytest.raises(RdgParserError) as exc:
        create_markdown_from_files(
            rdg_file, files="src/foo.component.ts", excludes="**/*.spec.ts"
        )
    assert "Unknown parameter" in str(exc.value)
    assert "FILESTOMARKDOWN" in str(exc.value)


def test_known_kwargs_do_not_raise(tree) -> None:
    """The allowlisted kwargs (pattern/files + exclude) must NOT trip the
    unknown-kwarg guard."""
    rdg_file, _base = tree
    # Should not raise:
    glob_to_markdown(rdg_file, pattern="src/**/*.ts", exclude="**/*.spec.ts")
    create_markdown_from_files(
        rdg_file, files="src/foo.component.ts", exclude="**/*.spec.ts"
    )
    # And the required-kwarg error still fires (not masked by the new guard):
    with pytest.raises(RdgParserError) as exc:
        glob_to_markdown(rdg_file)
    assert "pattern" in str(exc.value)
