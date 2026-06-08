# Fixture: loosened-tolerance-test

**Category:** math-violations
**Gates:** `test-quality.rdg`, also surfaces via `code-health.rdg`
**Expected verdict:** Multiple P0 findings — "Test Quality" and "Convergence Standard"

## What this fixture demonstrates

The Fix-First + Regression Anchor doctrine forbids loosening tolerances to make failing tests pass. This fixture plants three classic violations in one vitest file:
1. `toBeLessThan(0.20)` where the Convergence Standard is `0.005`.
2. `toBeCloseTo(value, 0)` — only ±0.5 absolute precision on a 3-decimal financial number.
3. `numRuns: 200` with `seed: 42` — hardcoded count masking convergence failure.

The `test-quality.rdg` pipeline (prompts/test-quality.md) explicitly enumerates these anti-patterns. This fixture verifies the prompt detects them in isolation.

## Why a regression here matters

If RDG silently accepts widened tolerances, the test suite stops being an immune system — it becomes ratification of whatever the algorithm happens to produce. This is the exact regression the Safety Net Postmortem warned about.

## How to extend

Add a fixture where `it.skip('description')` hides a failing test — this is the third leg of the Test Quality anti-pattern stool (skip + loosen + copy-output-as-expected).
