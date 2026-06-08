/**
 * Policy lookup helper used by the lifecycle MDP optimizer.
 *
 * This is a PLANTED VIOLATION FIXTURE — the `??` fallback on
 * line 18 silently substitutes a default allocation when the
 * policy table lookup misses. In production, this hides
 * convergence failures: a bug that produces undefined entries
 * in the policy tensor will surface as "everybody gets 60%
 * stock" instead of crashing visibly.
 *
 * The Boundary Rule (`docs/discipline/CLAUDE_ENG.md` §10):
 * defaults are acceptable at external boundaries (LLM output,
 * user input). Internal function-to-function data flow MUST
 * fail loudly.
 */

export function lookupPolicyAllocation(
  policy: number[][][],
  t: number,
  wealthIndex: number,
  humanCapitalIndex: number,
): number {
  // VIOLATION: silent fallback hides missing policy entries.
  // Expected RDG finding: P0 Safety Net Pattern — file:line — silent fallback.
  return policy[t]?.[wealthIndex]?.[humanCapitalIndex] ?? 0.6;
}

export function applyPolicyToWealth(
  policy: number[][][],
  t: number,
  wealth: number,
  humanCapital: number,
): number {
  const wIdx = Math.floor(wealth / 10000);
  const hcIdx = Math.floor(humanCapital / 10000);
  const allocation = lookupPolicyAllocation(policy, t, wIdx, hcIdx);
  return wealth * allocation;
}
