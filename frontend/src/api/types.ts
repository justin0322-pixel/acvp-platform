export type Envelope<T> = [{ acvVersion: string }, T];

export interface LoginResult {
  accessToken: string;
  largeEndpointRequired?: boolean;
  sizeConstraint?: number;
}

/** Spec 12.14.1: the server's catalogue of what it can test (`name`, not `algorithm`). */
export interface Algorithm {
  id: number;
  name: string;
  mode: string;
  revision: string;
}

/** Spec 12.5.2: every resource listing is a paged response. */
export interface Paged<T> {
  totalCount: number;
  incomplete: boolean;
  links: { first: string; next: string | null; prev: string | null; last: string };
  data: T[];
}

/** Spec 12.11 / 12.12 — what a certificate binds to. */
export interface ModuleResource {
  url: string;
  name: string;
  version?: string;
  type?: string;
  description?: string;
  vendorUrl?: string;
}

export interface OeResource {
  url: string;
  name: string;
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

export interface TestCase {
  tcId: number;
  [key: string]: any;
}

export interface TestGroup {
  tgId: number;
  testType: string;
  parameterSet?: string;
  tests: TestCase[];
  [key: string]: any;
}

export interface RetrySignal { vsId: number; retry: number; }
export interface ExpiredSignal { vsId: number; status: "expired"; }
export interface Prompt {
  vsId: number; algorithm: string; mode: string; revision: string;
  isSample?: boolean; testGroups: TestGroup[];
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
