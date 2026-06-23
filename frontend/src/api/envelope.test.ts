import { describe, it, expect } from "vitest";
import { wrap, unwrap } from "./envelope";

describe("ACVP envelope", () => {
  it("round-trips a payload", () => {
    expect(unwrap(wrap({ a: 1 }))).toEqual({ a: 1 });
  });

  it("puts acvVersion first", () => {
    const [version] = wrap({});
    expect(version).toHaveProperty("acvVersion");
  });
});
