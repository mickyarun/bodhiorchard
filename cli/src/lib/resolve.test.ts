import { describe, it, expect } from "vitest";
import { toContainerHost } from "./resolve.js";

describe("toContainerHost", () => {
  it("rewrites localhost and 127.0.0.1 hosts to host.docker.internal", () => {
    expect(toContainerHost("redis://localhost:6379")).toBe("redis://host.docker.internal:6379");
    expect(toContainerHost("postgresql+asyncpg://u:p@127.0.0.1:5432/db")).toBe(
      "postgresql+asyncpg://u:p@host.docker.internal:5432/db",
    );
  });

  it("leaves an already container-reachable host untouched", () => {
    const url = "postgresql+asyncpg://u:p@host.docker.internal:5432/db";
    expect(toContainerHost(url)).toBe(url);
  });

  it("does not rewrite a password or path that merely contains 'localhost'", () => {
    const url = "postgresql+asyncpg://u:localhost@db.example.com:5432/localhost";
    expect(toContainerHost(url)).toBe(url);
  });
});
