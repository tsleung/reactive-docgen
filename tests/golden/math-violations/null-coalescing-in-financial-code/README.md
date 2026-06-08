# Fixture: null-coalescing-in-financial-code

**Category:** math-violations
**Gates:** `code-health.rdg`
**Expected verdict:** P0 finding — "Safety Net Patterns"

## What this fixture demonstrates

The single most common Boundary Rule violation in the RtB codebase is the `optional?.chain ?? defaultValue` shape inside financial computation. This fixture plants that exact shape on a policy-tensor lookup and asserts that `code-health.rdg` emits a P0 finding pointing at the line.

## Why a regression here matters

If RDG silently downgrades or misses this pattern, the entire `code-health.rdg` pipeline becomes a placebo for the most important Boundary Rule check (`docs/discipline/CLAUDE_ENG.md` §10). The RDG prompt explicitly enumerates `?? defaultValue` as forbidden; this fixture verifies the prompt is calibrated to actually flag it.

## How to extend

Add additional inputs to `input/` to test variants — e.g., `|| fallback`, `try { ... } catch { return default; }`, `Math.max(0, x)` without a comment. Each new input should add a corresponding entry to `expected-output.md`'s `expectedFindings` array.

## Live mode

```sh
python tests/run-golden.py --live --filter math-violations/null-coalescing-in-financial-code
```

Runs the actual `code-health.rdg` pipeline against this fixture's `input/` and compares the LLM verdict against `expected-output.md`. Costs API calls; structural-mode is the default.
