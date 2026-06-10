import { describe, it, expect } from "vitest";
import { resolvePullPolicy } from "./docker.js";

describe("resolvePullPolicy", () => {
  it("passes through the supported relaxed policies", () => {
    expect(resolvePullPolicy("missing")).toBe("missing");
    expect(resolvePullPolicy("never")).toBe("never");
  });

  it("defaults to always for unset, empty, or unknown values", () => {
    expect(resolvePullPolicy(undefined)).toBe("always");
    expect(resolvePullPolicy("")).toBe("always");
    expect(resolvePullPolicy("always")).toBe("always");
    expect(resolvePullPolicy("bogus")).toBe("always");
  });
});
