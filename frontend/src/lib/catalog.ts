/** Algorithm catalog + registration builders that satisfy the backend's
 *  per-mode Pydantic validation (draft-celi-acvp-ml-kem / -ml-dsa). */
export interface FipsFamily {
  id: string; label: string; algorithm: string; modes: string[]; paramSets: string[];
}

export const FAMILIES: FipsFamily[] = [
  {
    id: "FIPS203", label: "FIPS 203 · ML-KEM", algorithm: "ML-KEM",
    modes: ["keyGen", "encapDecap"], paramSets: ["ML-KEM-512", "ML-KEM-768", "ML-KEM-1024"],
  },
  {
    id: "FIPS204", label: "FIPS 204 · ML-DSA", algorithm: "ML-DSA",
    modes: ["keyGen", "sigGen", "sigVer"], paramSets: ["ML-DSA-44", "ML-DSA-65", "ML-DSA-87"],
  },
];

/** Build one valid capability object for a mode + selected parameter sets. */
export function buildCapability(
  algorithm: string, mode: string, revision: string, parameterSets: string[],
): Record<string, unknown> {
  const base = { algorithm, mode, revision };

  if (algorithm === "ML-KEM" && mode === "keyGen") return { ...base, parameterSets };
  if (algorithm === "ML-KEM" && mode === "encapDecap")
    return { ...base, parameterSets, functions: ["encapsulation", "decapsulation"] };
  if (algorithm === "ML-DSA" && mode === "keyGen") return { ...base, parameterSets };

  // ML-DSA sigGen / sigVer share the capabilities/interface shape.
  const capabilities = [{ parameterSets, messageLength: [{ min: 8, max: 65536, increment: 8 }] }];
  if (mode === "sigGen")
    return {
      ...base, capabilities, deterministic: [true, false], externalMu: [false],
      signatureInterfaces: ["internal"], preHash: ["pure"],
    };
  return {
    ...base, capabilities, externalMu: [false],
    signatureInterfaces: ["internal"], preHash: ["pure"],
  };
}
