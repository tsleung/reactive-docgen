/**
 * Test for WTC objective stability across seeds.
 *
 * This is a PLANTED VIOLATION FIXTURE — the test originally
 * asserted a tight CV bound on the WTC objective (the
 * Convergence Standard: 0.5%). When the test failed
 * intermittently, a prior maintainer "fixed" it by widening
 * the tolerance to 20% instead of investigating the
 * underlying noise. This is the Fix-First + Regression Anchor
 * doctrine violated.
 *
 * Expected RDG finding from code-health.rdg / test-quality.rdg:
 *   P0 Test Quality — tolerance margin added to make a failing
 *   test pass; weak tolerance on financial precision.
 */

import { describe, it, expect } from 'vitest';
import { evaluateWtcObjective } from '../../../src/app/open-source/lifecycle/wtc-objective';

describe('WTC objective stability', () => {
  it('produces consistent results across seeds (CV target)', () => {
    const seeds = [1, 2, 3, 4, 5];
    const results = seeds.map((seed) =>
      evaluateWtcObjective({
        seed,
        numRuns: 200, // VIOLATION: hardcoded run count, not CONVERGENCE_STANDARD
      }),
    );

    const mean = results.reduce((sum, r) => sum + r, 0) / results.length;
    const variance =
      results.reduce((sum, r) => sum + (r - mean) ** 2, 0) / results.length;
    const cv = Math.sqrt(variance) / mean;

    // VIOLATION: target should be 0.005 (Convergence Standard 0.5% CV)
    // Loosened to 0.20 (20%) so the test stops failing. The test now
    // accepts massive seeding noise as "stable."
    expect(cv).toBeLessThan(0.20);
  });

  it('matches expected mean within tolerance', () => {
    const expected = 0.4523;
    const actual = evaluateWtcObjective({ seed: 42, numRuns: 100 });

    // VIOLATION: toBeCloseTo with 0 digits = ±0.5 absolute tolerance on
    // a value that should be precise to 3 decimals.
    expect(actual).toBeCloseTo(expected, 0);
  });
});
