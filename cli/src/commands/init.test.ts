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

// `glideship init` against a temp directory: files written, secrets kept on
// re-run, and nothing touched when the user declines. Docker, port probing and
// prompts are faked; the filesystem is real.
import { describe, it, expect, beforeEach, afterEach, vi } from "vitest";
import fs from "fs-extra";
import os from "node:os";
import path from "node:path";

const mocks = vi.hoisted(() => ({
  compose: vi.fn(),
  prompt: vi.fn(),
  resolveServices: vi.fn(),
  warn: vi.fn(),
}));
vi.mock("../lib/preflight.js", () => ({ preflight: vi.fn(async () => undefined) }));
vi.mock("../lib/docker.js", () => ({ compose: mocks.compose }));
vi.mock("../lib/resolve.js", () => ({ resolveServices: mocks.resolveServices }));
vi.mock("inquirer", () => ({ default: { prompt: mocks.prompt } }));
vi.mock("../lib/ui.js", () => ({
  banner: vi.fn(),
  log: { info: vi.fn(), step: vi.fn(), success: vi.fn(), warn: mocks.warn, error: vi.fn(), plain: vi.fn() },
}));

import { initCommand } from "./init.js";
import { configPath, readConfig, type ProjectConfig } from "../lib/config.js";
import { composeFilePath, envFilePath } from "../lib/project.js";
import { parseSecretsFromEnv } from "../lib/env.js";

const SERVICES: ProjectConfig["services"] = {
  postgres: { mode: "bundled", hostPort: 5433 },
  redis: { mode: "bundled", hostPort: 6379 },
  backend: { hostPort: 8000 },
  frontend: { hostPort: 3001 },
  multiplayer: { hostPort: 2567 },
};
const OPTS = { yes: false, allowPostgresReuse: false, imageTag: "1.2.0" };

let dir: string;

beforeEach(async () => {
  dir = path.join(await fs.mkdtemp(path.join(os.tmpdir(), "glideship-init-")), "install");
  mocks.compose.mockReset().mockResolvedValue({ code: 0, stdout: "", stderr: "" });
  mocks.prompt.mockReset();
  mocks.resolveServices.mockReset().mockResolvedValue(SERVICES);
  mocks.warn.mockReset();
});

afterEach(async () => {
  await fs.remove(path.dirname(dir));
});

describe("glideship init", () => {
  it("scaffolds compose, .env, config and .gitignore, then pulls images", async () => {
    await initCommand(dir, OPTS);

    const compose = await fs.readFile(composeFilePath(dir), "utf8");
    expect(compose).toContain("mickyarun/glideship-backend:${IMAGE_TAG}");
    const env = await fs.readFile(envFilePath(dir), "utf8");
    expect(env).toContain("IMAGE_TAG=1.2.0\n");
    expect(env).toContain("FRONTEND_HOST_PORT=3001\n");
    expect(parseSecretsFromEnv(env)?.HR_ENCRYPTION_KEYS).toMatch(/^k[0-9a-f]{6}:/);
    expect(await readConfig(dir)).toMatchObject({ imageTag: "1.2.0", services: SERVICES });
    expect(await fs.readFile(path.join(dir, ".gitignore"), "utf8")).toMatch(/^\.env$/m);
    expect(mocks.compose).toHaveBeenCalledWith(dir, ["-p", "bodhiorchard", "pull"], {
      inherit: true,
    });
  });

  it.skipIf(process.platform === "win32")("keeps .env readable by the owner only", async () => {
    await initCommand(dir, OPTS);
    expect((await fs.stat(envFilePath(dir))).mode & 0o777).toBe(0o600);
  });

  it("generates different secrets for different installs", async () => {
    await initCommand(dir, OPTS);
    const other = `${dir}-2`;
    await initCommand(other, OPTS);
    const a = parseSecretsFromEnv(await fs.readFile(envFilePath(dir), "utf8"));
    const b = parseSecretsFromEnv(await fs.readFile(envFilePath(other), "utf8"));
    expect(a?.SECRET_KEY).not.toBe(b?.SECRET_KEY);
    expect(a?.COLYSEUS_BRIDGE_SECRET).not.toBe(b?.COLYSEUS_BRIDGE_SECRET);
    await fs.remove(other);
  });

  it("re-running with --yes keeps every secret and a customised .gitignore", async () => {
    await initCommand(dir, OPTS);
    const before = parseSecretsFromEnv(await fs.readFile(envFilePath(dir), "utf8"));
    await fs.writeFile(path.join(dir, ".gitignore"), ".env\nmy-notes.txt\n");

    await initCommand(dir, { ...OPTS, yes: true });

    const after = parseSecretsFromEnv(await fs.readFile(envFilePath(dir), "utf8"));
    expect(after).toEqual(before);
    expect(await fs.readFile(path.join(dir, ".gitignore"), "utf8")).toContain("my-notes.txt");
    expect(mocks.prompt).not.toHaveBeenCalled();
  });

  it("changes nothing when the user declines to re-run over an install", async () => {
    await initCommand(dir, OPTS);
    const envBefore = await fs.readFile(envFilePath(dir), "utf8");
    const configBefore = await fs.readFile(configPath(dir), "utf8");
    mocks.compose.mockClear();
    mocks.resolveServices.mockClear();
    mocks.prompt.mockResolvedValue({ proceed: false });

    await initCommand(dir, { ...OPTS, imageTag: "9.9.9" });

    expect(await fs.readFile(envFilePath(dir), "utf8")).toBe(envBefore);
    expect(await fs.readFile(configPath(dir), "utf8")).toBe(configBefore);
    expect(mocks.resolveServices).not.toHaveBeenCalled();
    expect(mocks.compose).not.toHaveBeenCalled();
  });

  it("applies the new options when the user confirms a re-run", async () => {
    await initCommand(dir, OPTS);
    mocks.prompt.mockResolvedValue({ proceed: true });
    await initCommand(dir, { ...OPTS, imageTag: "1.3.0" });
    expect((await readConfig(dir)).imageTag).toBe("1.3.0");
  });

  it("still writes the install when the image pull fails, and says so", async () => {
    mocks.compose.mockResolvedValue({ code: 1, stdout: "", stderr: "network" });
    await expect(initCommand(dir, OPTS)).resolves.toBeUndefined();
    expect(await fs.pathExists(configPath(dir))).toBe(true);
    expect(mocks.warn).toHaveBeenCalledWith(expect.stringMatching(/start` will retry/));
  });

  it("aborts before writing anything when an existing .env lost its secrets", async () => {
    await fs.outputFile(envFilePath(dir), "SECRET_KEY=only-one\n");
    await expect(initCommand(dir, { ...OPTS, yes: true })).rejects.toThrow(
      /Restore it from backup/,
    );
    expect(await fs.pathExists(configPath(dir))).toBe(false);
    expect(await fs.readFile(envFilePath(dir), "utf8")).toBe("SECRET_KEY=only-one\n");
  });

  it("propagates an aborted port prompt without writing files", async () => {
    mocks.resolveServices.mockRejectedValue(new Error("Setup aborted by user."));
    await expect(initCommand(dir, OPTS)).rejects.toThrow("Setup aborted by user.");
    expect(await fs.pathExists(dir)).toBe(false);
  });
});
