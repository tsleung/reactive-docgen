# Fixture: converged-false-false-positive (bias anchor)

**Category:** llm-bias-anchor
**Gates:** `code-health.rdg`
**Expected verdict:** PASS — no findings

## What this fixture demonstrates

This is a NEGATIVE-SPACE fixture. The code is correct. The fixture asserts RDG produces PASS, not findings. It anchors the prompt-precision fix for False Positive Triage Methodology category #4 (`converged: false` vs safety net) from the 2026-03-13 incident.

If a future prompt revision regresses — i.e., starts flagging `converged: false` as a safety net again — this fixture flips from PASS to FAIL and the runner surfaces the regression.

## Why a regression here matters

LLM-auditing-LLM bias compounds. Without anchored fixtures for previously-corrected FPs, the substrate has no memory: each prompt revision risks bringing back the same FP. This is the regression anchor that makes the False Positive Triage Methodology durable.

## How to extend

The False Positive Triage Methodology lists 6 categories. This fixture covers #4. Add fixtures for the other five:
1. Exploratory vs production convergence (`_TEST_FAST_PRESET` flagged as safety net)
2. Default parameter vs fixed count (`minSimulations: 500` flagged as hardcoded)
3. Test seed vs production seed (`seed: 42` in `.vitest.ts`)
4. **`converged: false` vs safety net** ← this fixture
5. Experimental vs production code (`@experimental` with relaxed CV flagged)
6. Aspirational TODO vs rationalization (phase-gated plans flagged as excuse-making)
