import { describe, it, expect } from "vitest";
import YAML from "yaml";
import { renderComposeFile } from "./compose.js";
import { CONFIG_VERSION, PROJECT_NAME, type ProjectConfig } from "./config.js";

function baseConfig(overrides: Partial<ProjectConfig["services"]> = {}): ProjectConfig {
  return {
    version: CONFIG_VERSION,
    project: PROJECT_NAME,
    imageTag: "latest",
    services: {
      postgres: { mode: "bundled", hostPort: 5432 },
      redis: { mode: "bundled", hostPort: 6379 },
      backend: { hostPort: 8000 },
      frontend: { hostPort: 3000 },
      multiplayer: { hostPort: 2567 },
      ...overrides,
    },
  };
}

describe("renderComposeFile — bundled infra", () => {
  const doc = YAML.parse(renderComposeFile(baseConfig()));

  it("emits valid compose with all five services", () => {
    expect(Object.keys(doc.services).sort()).toEqual(
      ["backend", "frontend", "multiplayer", "postgres", "redis"].sort(),
    );
  });

  it("templates host ports and image tags", () => {
    expect(doc.services.postgres.ports).toContain("${POSTGRES_HOST_PORT}:5432");
    expect(doc.services.frontend.ports).toContain("${FRONTEND_HOST_PORT}:80");
    expect(doc.services.backend.image).toBe("mickyarun/bodhiorchard-backend:${IMAGE_TAG}");
  });

  it("declares the postgres_data volume and backend depends_on", () => {
    expect(doc.volumes).toHaveProperty("postgres_data");
    expect(doc.services.backend.depends_on.postgres.condition).toBe("service_healthy");
    expect(doc.services.backend.extra_hosts).toBeUndefined();
  });
});

describe("renderComposeFile — reused postgres", () => {
  const doc = YAML.parse(
    renderComposeFile(
      baseConfig({ postgres: { mode: "reuse", url: "postgresql+asyncpg://u:p@host.docker.internal:5432/db" } }),
    ),
  );

  it("omits the postgres service and its volume", () => {
    expect(doc.services).not.toHaveProperty("postgres");
    expect(doc.volumes).not.toHaveProperty("postgres_data");
  });

  it("drops the postgres depends_on entry but keeps redis", () => {
    expect(doc.services.backend.depends_on).not.toHaveProperty("postgres");
    expect(doc.services.backend.depends_on.redis.condition).toBe("service_healthy");
  });

  it("adds host-gateway extra_hosts so the container can reach the host", () => {
    expect(doc.services.backend.extra_hosts).toContain("host.docker.internal:host-gateway");
  });
});
