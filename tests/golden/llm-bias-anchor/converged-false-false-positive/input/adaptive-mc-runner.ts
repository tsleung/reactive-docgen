/**
 * Adaptive Monte Carlo runner used by the lifecycle pipeline.
 *
 * BIAS-ANCHOR FIXTURE — this code is CORRECT. The function below
 * returns `{ converged: false }` when the CV target is not met.
 * This is HONEST STATUS REPORTING, not a safety-net pattern.
 *
 * Past RDG runs (2026-03-13 incident: 20% FP rate on math findings
 * documented in RDG_GOVERNANCE_REPORTS_PLAYBOOK.md §False Positive
 * Triage Methodology, category 4 — "`converged: false` vs safety
 * net") incorrectly flagged this exact shape as a P0 safety net.
 *
 * The Authority Doctrine response was a PROMPT-PRECISION fix:
 * the prompt now whitelists `converged: false` as legitimate
 * status reporting. This fixture pins that whitelist down — if a
 * future prompt revision regresses, the FP comes back.
 *
 * Caller contract: callers MUST check the `converged` flag and
 * decide what to do with non-convergence (retry, surface to user,
 * fail loudly). Returning `converged: false` is NOT swallowing
 * the failure — it is reporting it.
 */

import { CONVERGENCE_STANDARD } from './convergence-standard';

export interface AdaptiveMcResult {
  readonly mean: number;
  readonly stdDev: number;
  readonly cv: number;
  readonly numRuns: number;
  readonly converged: boolean; // honest status, NOT a safety net
}

export function runAdaptiveMc(
  evaluator: (seed: number) => number,
  targetCv: number = CONVERGENCE_STANDARD.targetCv,
  maxRuns: number = CONVERGENCE_STANDARD.maxRuns,
): AdaptiveMcResult {
  const results: number[] = [];
  for (let i = 0; i < maxRuns; i++) {
    results.push(evaluator(i));
    if (i >= CONVERGENCE_STANDARD.minRuns) {
      const mean = results.reduce((s, r) => s + r, 0) / results.length;
      const variance =
        results.reduce((s, r) => s + (r - mean) ** 2, 0) / results.length;
      const stdDev = Math.sqrt(variance);
      const cv = stdDev / Math.abs(mean);
      if (cv < targetCv) {
        return { mean, stdDev, cv, numRuns: results.length, converged: true };
      }
    }
  }

  // Did not converge within maxRuns — return HONEST status.
  // The caller (not this function) decides whether to retry,
  // surface to user, or fail loudly. This is the §False Positive
  // Triage category 4 pattern: `converged: false` is reporting,
  // not hiding.
  const mean = results.reduce((s, r) => s + r, 0) / results.length;
  const variance =
    results.reduce((s, r) => s + (r - mean) ** 2, 0) / results.length;
  const stdDev = Math.sqrt(variance);
  const cv = stdDev / Math.abs(mean);
  return { mean, stdDev, cv, numRuns: results.length, converged: false };
}
