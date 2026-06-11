import { describe, it, expect } from "vitest";
import { renderEnvFile, parseSecretsFromEnv } from "./env.js";
import { generateSecrets } from "./secrets.js";
import { CONFIG_VERSION, PROJECT_NAME, type ProjectConfig } from "./config.js";

const secrets = generateSecrets();

function config(overrides: Partial<ProjectConfig["services"]> = {}): ProjectConfig {
  return {
    version: CONFIG_VERSION,
    project: PROJECT_NAME,
    imageTag: "latest",
    services: {
      postgres: { mode: "bundled", hostPort: 5544 },
      redis: { mode: "bundled", hostPort: 6379 },
      backend: { hostPort: 8000 },
      frontend: { hostPort: 3000 },
      multiplayer: { hostPort: 2567 },
      ...overrides,
    },
  };
}

describe("renderEnvFile", () => {
  it("uses in-network DNS URLs for bundled infra and emits the remapped host port", () => {
    const env = renderEnvFile(config(), secrets);
    expect(env).toContain("POSTGRES_HOST_PORT=5544");
    expect(env).toContain(
      "DATABASE_URL=postgresql+asyncpg://bodhiorchard:bodhiorchard@postgres:5432/bodhiorchard",
    );
    expect(env).toContain("REDIS_URL=redis://redis:6379");
    expect(env).toContain("ANTHROPIC_API_KEY=");
  });

  it("uses the captured URL and omits the host port for reused infra", () => {
    const env = renderEnvFile(
      config({ redis: { mode: "reuse", url: "redis://host.docker.internal:6379" } }),
      secrets,
    );
    expect(env).toContain("REDIS_URL=redis://host.docker.internal:6379");
    expect(env).not.toContain("REDIS_HOST_PORT=");
  });
});

describe("parseSecretsFromEnv", () => {
  it("round-trips the generated secrets", () => {
    const env = renderEnvFile(config(), secrets);
    expect(parseSecretsFromEnv(env)).toEqual(secrets);
  });

  it("returns null when a secret is missing", () => {
    expect(parseSecretsFromEnv("SECRET_KEY=abc\nENCRYPTION_KEY=def\n")).toBeNull();
  });
});
