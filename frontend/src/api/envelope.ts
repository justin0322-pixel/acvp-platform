import type { Envelope } from "./types";

const ACV = (import.meta.env.VITE_ACV_VERSION as string) ?? "1.0";

// Wrap a payload in the ACVP version envelope: [{acvVersion}, payload].
export function wrap<T>(payload: T): Envelope<T> {
  return [{ acvVersion: ACV }, payload];
}

// Validate the envelope and return the inner payload.
export function unwrap<T>(body: Envelope<T>): T {
  if (!Array.isArray(body) || body.length < 2) {
    throw new Error("malformed ACVP envelope");
  }
  return body[1];
}
