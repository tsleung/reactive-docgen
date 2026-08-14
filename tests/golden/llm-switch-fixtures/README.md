# LLM-Switch Fixtures (S11 regression anchor)

**Story:** S11 — RDG LLM-Switch Predicate Layer
**Plan:** `docs/plans/2026-05-17_codification-doctrine-substrate-health.md` §S11
**Convention 6 threshold:** switch becomes load-bearing only when `divergence_rate < 0.05 AND total_invocations >= 20 AND shadow_duration_days >= 14`.

## What lives here

Hand-graded diffs, each labeled `{ "substantialChange": true | false }`. The S11 predicate (yet to be implemented at `rdg-notebook/reactive-docgen/src/rdg/switch.py`) will be evaluated against these fixtures to compute the divergence rate that gates promotion to load-bearing.

A diff is `substantialChange: true` when re-running the upstream RDG pipeline is justified — the change affects what the audit would say. A diff is `substantialChange: false` when re-running would waste API calls — the change is cosmetic, formatting, comment-only, or otherwise invisible to the audit.

## Fixture format

Each fixture is a single JSON file under `cases/` named `<NNN>-<short-slug>.json`:

```json
{
  "schemaVersion": "1.0",
  "fixtureId": "NNN-short-slug",
  "pipeline": "code-health.rdg | content-doctrine.rdg | ...",
  "facet": "what the diff is meant to test (algorithmic / cosmetic / scope / etc.)",
  "before": "...verbatim before content...",
  "after": "...verbatim after content...",
  "label": {
    "substantialChange": true,
    "rationale": "Why a human grader assigned this label."
  },
  "graderNotes": "Optional commentary for future re-grading."
}
```

## Scaffolded count

- **10 illustrative entries shipped with S10** spanning both labels and several common diff facets.
- **~40 more required for S11 promotion** — the Convention 6 statistical floor is 20 invocations, but the plan calls for a ~50-entry hand-graded set to give the predicate room to demonstrate divergence_rate < 0.05.

## Use by S11

S11's `switch.py` runs each `before` → `after` diff through the predicate and produces a `{ substantialChange: bool }` prediction. The predicate's prediction is compared against `label.substantialChange`. Divergences are logged to `docs/operations/LLM_SWITCH_SHADOW_DIVERGENCE.generated.md` (per Convention 1) and aggregated against the Convention 6 threshold.

## Use by golden-test runner

`run-golden.py --switch-fixtures` validates the schema of every fixture file: required keys present, label boolean is a bool, before/after are strings, no empty entries. It does NOT execute the S11 predicate (S11 is not yet implemented). When S11 ships, the runner gains `--live-switch` to invoke the predicate.

## Adding fixtures

Append to `cases/` with the next sequential number. Avoid renumbering existing fixtures (would scramble historical divergence stats once S11 is live).

## Calibration discipline

Hand-graders MUST record their rationale in `label.rationale` so disagreements at re-grade time produce a traceable conversation. If two graders disagree on a fixture, the case is filed humanGated for founder adjudication — DO NOT silently overwrite a previous label.
