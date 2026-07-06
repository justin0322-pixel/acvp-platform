import type { Prompt } from "../api/types";

/**
 * Build a submission body covering every tcId in the prompt. The real DUT would
 * fill in algorithm-specific answer fields; the server's structural check only
 * requires the tcIds to match the prompt (missing ones grade "missing").
 */
export function buildResponse(prompt: Prompt): Record<string, unknown> {
  return {
    vsId: prompt.vsId,
    testGroups: (prompt.testGroups ?? []).map((g: any) => ({
      tgId: g.tgId,
      tests: (g.tests ?? []).map((t: any) => ({ tcId: t.tcId })),
    })),
  };
}
