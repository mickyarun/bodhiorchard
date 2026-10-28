// Copyright 2025-2026 Arun Rajkumar
//
// Licensed under the Apache License, Version 2.0 (the "License");
// you may not use this file except in compliance with the License.
// You may obtain a copy of the License at
//
//     http://www.apache.org/licenses/LICENSE-2.0
//
// Unless required by applicable law or agreed to in writing, software
// distributed under the License is distributed on an "AS IS" BASIS,
// WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
// See the License for the specific language governing permissions and
// limitations under the License.

// Persisted installer config: round trip, actionable errors, and paths built
// with the host platform's separator.
import { describe, it, expect, beforeEach, afterEach } from "vitest";
import fs from "fs-extra";
import os from "node:os";
import path from "node:path";
import {
  CONFIG_DIR,
  CONFIG_FILE,
  CONFIG_VERSION,
  PROJECT_NAME,
  configExists,
  configPath,
  readConfig,
  writeConfig,
  type ProjectConfig,
} from "./config.js";

const config: ProjectConfig = {
  version: CONFIG_VERSION,
  project: PROJECT_NAME,
  imageTag: "1.2.0",
  services: {
    postgres: { mode: "reuse", url: "postgresql+asyncpg://u:p@host.docker.internal:5432/db" },
    redis: { mode: "bundled", hostPort: 6380 },
    backend: { hostPort: 8001 },
    frontend: { hostPort: 3001 },
    multiplayer: { hostPort: 2568 },
  },
};

describe("installer config", () => {
  let dir: string;
  beforeEach(async () => {
    dir = await fs.mkdtemp(path.join(os.tmpdir(), "glideship-config-"));
  });
  afterEach(async () => {
    await fs.remove(dir);
  });

  it("keeps the config inside the legacy .bodhiorchard folder", () => {
    expect(configPath(dir)).toBe(path.join(dir, CONFIG_DIR, CONFIG_FILE));
    expect(CONFIG_DIR).toBe(".bodhiorchard");
  });

  it("round-trips every service decision", async () => {
    await writeConfig(dir, config);
    expect(await configExists(dir)).toBe(true);
    expect(await readConfig(dir)).toEqual(config);
  });

  it("writes human-readable JSON so users can edit host ports", async () => {
    await writeConfig(dir, config);
    const raw = await fs.readFile(configPath(dir), "utf8");
    expect(raw).toContain('\n  "imageTag": "1.2.0"');
  });

  it("explains how to recover when no config exists", async () => {
    expect(await configExists(dir)).toBe(false);
    await expect(readConfig(dir)).rejects.toThrow(/Run `glideship init` first/);
    await expect(readConfig(dir)).rejects.toThrow(/--project-dir/);
  });

  it("refuses a config written by an incompatible CLI version", async () => {
    await writeConfig(dir, { ...config, version: CONFIG_VERSION + 1 });
    await expect(readConfig(dir)).rejects.toThrow(
      `Config version ${CONFIG_VERSION + 1} is not supported`,
    );
  });

  it("surfaces a corrupt config file instead of guessing", async () => {
    await fs.outputFile(configPath(dir), "{ not json");
    await expect(readConfig(dir)).rejects.toThrow();
  });

  it("overwrites the previous config on re-init", async () => {
    await writeConfig(dir, config);
    await writeConfig(dir, { ...config, imageTag: "latest" });
    expect((await readConfig(dir)).imageTag).toBe("latest");
  });
});
