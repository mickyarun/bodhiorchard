import { describe, it, expect, beforeEach, afterEach, vi } from "vitest";
import fs from "fs-extra";
import os from "node:os";
import path from "node:path";
import { loadSecrets, materialize, envFilePath } from "./project.js";
import { CONFIG_VERSION, PROJECT_NAME, type ProjectConfig } from "./config.js";

const config: ProjectConfig = {
  version: CONFIG_VERSION,
  project: PROJECT_NAME,
  imageTag: "latest",
  services: {
    postgres: { mode: "bundled", hostPort: 5432 },
    redis: { mode: "bundled", hostPort: 6379 },
    backend: { hostPort: 8000 },
    frontend: { hostPort: 3000 },
    multiplayer: { hostPort: 2567 },
  },
};
const OLD_ENV = "SECRET_KEY=a\nENCRYPTION_KEY=b\nCOLYSEUS_BRIDGE_SECRET=c\n";

describe("loadSecrets and the HR keyring", () => {
  let dir: string;
  beforeEach(async () => {
    dir = await fs.mkdtemp(path.join(os.tmpdir(), "bo-project-"));
    vi.spyOn(console, "warn").mockImplementation(() => {});
  });
  afterEach(async () => {
    vi.restoreAllMocks();
    await fs.remove(dir);
  });

  it("gives an install from before HR records a keyring once, then keeps it", async () => {
    await fs.writeFile(envFilePath(dir), OLD_ENV);
    const first = await loadSecrets(dir);
    expect(first.HR_ENCRYPTION_KEYS).toMatch(/^k[0-9a-f]{6}:/);
    await materialize(dir, config, first);
    expect((await loadSecrets(dir)).HR_ENCRYPTION_KEYS).toBe(first.HR_ENCRYPTION_KEYS);
  });

  it("refuses to replace a keyring that went missing after it was issued", async () => {
    await fs.writeFile(envFilePath(dir), OLD_ENV);
    await materialize(dir, config, await loadSecrets(dir));
    // e.g. an .env backup from before the key existed is restored
    await fs.writeFile(envFilePath(dir), OLD_ENV);
    await expect(loadSecrets(dir)).rejects.toThrow(/Restore it from backup/);
  });
});
