import { describe, it, expect } from "vitest";
import { generateSecrets } from "./secrets.js";

describe("generateSecrets", () => {
  it("produces three distinct 64-char hex secrets", () => {
    const s = generateSecrets();
    for (const value of [s.SECRET_KEY, s.ENCRYPTION_KEY, s.COLYSEUS_BRIDGE_SECRET]) {
      expect(value).toMatch(/^[0-9a-f]{64}$/);
    }
    expect(new Set([s.SECRET_KEY, s.ENCRYPTION_KEY, s.COLYSEUS_BRIDGE_SECRET]).size).toBe(3);
  });

  it("is non-deterministic across calls", () => {
    expect(generateSecrets().SECRET_KEY).not.toBe(generateSecrets().SECRET_KEY);
  });
});
