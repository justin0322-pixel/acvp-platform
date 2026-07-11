export type Envelope<T> = [{ acvVersion: string }, T];

export interface LoginResult {
  accessToken: string;
  largeEndpointRequired?: boolean;
  sizeConstraint?: number;
}

export interface Algorithm {
  algorithm: string;
  mode: string;
  revision: string;
}

/** The test-session object returned by POST /testSessions (carries accessToken). */
export interface SessionObject {
  url: string;
  acvpVersion: string;
  createdOn: string;
  expiresOn: string;
  encryptAtRest: boolean;
  publishable: boolean;
  passed: boolean;
  isSample: boolean;
  vectorSetUrls: string[];
  accessToken: string;
}

/** GET /testSessions/{id} — same object minus the token, with a pointer URL. */
export interface SessionInfo {
  url: string;
  acvpVersion: string;
  createdOn: string;
  expiresOn: string;
  encryptAtRest: boolean;
  publishable: boolean;
  passed: boolean;
  isSample: boolean;
  vectorSetsUrl: string;
}

export type Disposition =
  | "passed" | "failed" | "incomplete" | "unreceived" | "missing" | "expired" | "error";

export interface RetrySignal { vsId: number; retry: number; }
export interface ExpiredSignal { vsId: number; status: "expired"; }
export interface Prompt {
  vsId: number; algorithm: string; mode: string; revision: string;
  isSample?: boolean; testGroups: any[];
}
export type VectorSetResponse = Prompt | RetrySignal | ExpiredSignal;

export interface VectorResults {
  results: { vsId: number; disposition: Disposition; tests: { tcId: number; result: string }[] };
}
export interface SessionResults {
  passed: boolean;
  results: { vectorSetUrl: string; status: Disposition }[];
}
export interface RequestObject {
  url: string; status: "initial" | "processing" | "approved" | "rejected" | "error";
  approvedUrl?: string; message?: string;
}

export function isRetry(v: VectorSetResponse): v is RetrySignal {
  return (v as RetrySignal).retry !== undefined;
}
export function isExpired(v: VectorSetResponse): v is ExpiredSignal {
  return (v as ExpiredSignal).status === "expired";
}
