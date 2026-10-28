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

// start / stop / status / logs / reset / update against a real temp install.
// Docker Compose, health polling, prompts and the browser are faked.
import { describe, it, expect, beforeEach, afterEach, vi } from "vitest";
import fs from "fs-extra";
import os from "node:os";
import path from "node:path";

const mocks = vi.hoisted(() => ({
  compose: vi.fn(),
  prompt: vi.fn(),
  waitForHealth: vi.fn(),
  openBrowser: vi.fn(),
  info: vi.fn(),
}));
vi.mock("../lib/preflight.js", () => ({ preflight: vi.fn(async () => undefined) }));
vi.mock("../lib/docker.js", async (importOriginal) => ({
  ...(await importOriginal<typeof import("../lib/docker.js")>()),
  compose: mocks.compose,
}));
vi.mock("../lib/health.js", () => ({ waitForHealth: mocks.waitForHealth }));
vi.mock("inquirer", () => ({ default: { prompt: mocks.prompt } }));
vi.mock("../lib/ui.js", () => {
  const spin = { start: () => spin, succeed: vi.fn(), warn: vi.fn() };
  return {
    log: { info: mocks.info, step: vi.fn(), success: vi.fn(), warn: vi.fn(), error: vi.fn(), plain: vi.fn() },
    spinner: () => spin,
    openBrowser: mocks.openBrowser,
  };
});

import { startCommand } from "./start.js";
import { stopCommand } from "./stop.js";
import { statusCommand } from "./status.js";
import { logsCommand } from "./logs.js";
import { resetCommand } from "./reset.js";
import { updateCommand } from "./update.js";
import { CONFIG_VERSION, PROJECT_NAME, readConfig, writeConfig, type ProjectConfig } from "../lib/config.js";
import { composeFilePath, envFilePath, materialize } from "../lib/project.js";
import { generateSecrets } from "../lib/secrets.js";
import { parseSecretsFromEnv } from "../lib/env.js";

const CONFIG: ProjectConfig = {
  version: CONFIG_VERSION,
  project: PROJECT_NAME,
  imageTag: "1.2.0",
  services: {
    postgres: { mode: "bundled", hostPort: 5432 },
    redis: { mode: "bundled", hostPort: 6379 },
    backend: { hostPort: 8001 },
    frontend: { hostPort: 3001 },
    multiplayer: { hostPort: 2567 },
  },
};

let dir: string;

function composeArgs(): string[][] {
  return mocks.compose.mock.calls.map(([, args]) => args as string[]);
}

beforeEach(async () => {
  dir = await fs.mkdtemp(path.join(os.tmpdir(), "glideship-life-"));
  await writeConfig(dir, CONFIG);
  await materialize(dir, CONFIG, generateSecrets());
  mocks.compose.mockReset().mockResolvedValue({ code: 0, stdout: "", stderr: "" });
  mocks.prompt.mockReset();
  mocks.waitForHealth.mockReset().mockResolvedValue(true);
  mocks.openBrowser.mockReset();
  mocks.info.mockReset();
});

afterEach(async () => {
  process.exitCode = undefined;
  vi.unstubAllEnvs();
  await fs.remove(dir);
});

describe("glideship start", () => {
  it("brings the stack up, waits on the configured ports and opens setup", async () => {
    await startCommand(dir);
    expect(composeArgs()).toEqual([["-p", "bodhiorchard", "up", "-d", "--pull", "always"]]);
    expect(mocks.waitForHealth).toHaveBeenCalledWith(8001, 3001);
    expect(mocks.openBrowser).toHaveBeenCalledWith("http://localhost:3001/setup");
  });

  it("honours BODHIORCHARD_PULL=missing for locally built images", async () => {
    vi.stubEnv("BODHIORCHARD_PULL", "missing");
    await startCommand(dir);
    expect(composeArgs()[0]).toEqual(["-p", "bodhiorchard", "up", "-d", "--pull", "missing"]);
  });

  it("re-creates a deleted compose file from the saved config", async () => {
    await fs.remove(composeFilePath(dir));
    await startCommand(dir);
    expect(await fs.readFile(composeFilePath(dir), "utf8")).toContain("glideship-frontend");
  });

  it("stops with exit code 1 and skips health checks when compose up fails", async () => {
    mocks.compose.mockResolvedValue({ code: 1, stdout: "", stderr: "" });
    await startCommand(dir);
    expect(process.exitCode).toBe(1);
    expect(mocks.waitForHealth).not.toHaveBeenCalled();
    expect(mocks.openBrowser).not.toHaveBeenCalled();
  });

  it("tells the user to run init when there is no install", async () => {
    const empty = await fs.mkdtemp(path.join(os.tmpdir(), "glideship-empty-"));
    await expect(startCommand(empty)).rejects.toThrow(/Run `glideship init` first/);
    expect(mocks.compose).not.toHaveBeenCalled();
    await fs.remove(empty);
  });

  it("refuses to start when .env is missing rather than minting new secrets", async () => {
    await fs.remove(envFilePath(dir));
    await expect(startCommand(dir)).rejects.toThrow(/Missing \.env/);
    expect(mocks.compose).not.toHaveBeenCalled();
  });
});

describe("stop, status and logs", () => {
  it("stop keeps volumes and reports compose failures", async () => {
    await stopCommand(dir);
    expect(composeArgs()).toEqual([["-p", "bodhiorchard", "down"]]);
    mocks.compose.mockResolvedValue({ code: 2, stdout: "", stderr: "" });
    await stopCommand(dir);
    expect(process.exitCode).toBe(1);
  });

  it("status prints the URLs for the configured host ports", async () => {
    await statusCommand(dir);
    expect(composeArgs()).toEqual([["-p", "bodhiorchard", "ps"]]);
    expect(mocks.info).toHaveBeenCalledWith("Frontend: http://localhost:3001/");
    expect(mocks.info).toHaveBeenCalledWith("Backend:  http://localhost:8001/");
  });

  it("logs follows one service or all of them", async () => {
    await logsCommand(dir, "backend");
    await logsCommand(dir);
    expect(composeArgs()).toEqual([
      ["-p", "bodhiorchard", "logs", "-f", "backend"],
      ["-p", "bodhiorchard", "logs", "-f"],
    ]);
  });
});

describe("glideship reset", () => {
  it("deletes nothing when the user declines", async () => {
    mocks.prompt.mockResolvedValue({ confirm: false });
    await resetCommand(dir, { yes: false });
    expect(mocks.compose).not.toHaveBeenCalled();
  });

  it("removes containers and volumes with --yes, without prompting", async () => {
    await resetCommand(dir, { yes: true });
    expect(mocks.prompt).not.toHaveBeenCalled();
    expect(composeArgs()).toEqual([["-p", "bodhiorchard", "down", "-v"]]);
  });
});

describe("glideship update", () => {
  it("pins a new tag into config and .env, then pulls and restarts", async () => {
    const secretsBefore = parseSecretsFromEnv(await fs.readFile(envFilePath(dir), "utf8"));
    await updateCommand(dir, { tag: "1.3.0" });
    expect((await readConfig(dir)).imageTag).toBe("1.3.0");
    const env = await fs.readFile(envFilePath(dir), "utf8");
    expect(env).toContain("IMAGE_TAG=1.3.0\n");
    expect(parseSecretsFromEnv(env)).toEqual(secretsBefore);
    expect(composeArgs()).toEqual([
      ["-p", "bodhiorchard", "pull"],
      ["-p", "bodhiorchard", "up", "-d"],
    ]);
  });

  it("refuses to update an install whose .env is missing, before pulling", async () => {
    await fs.remove(envFilePath(dir));
    await expect(updateCommand(dir, {})).rejects.toThrow(/Missing \.env/);
    expect(mocks.compose).not.toHaveBeenCalled();
  });

  it("refuses to update an install whose .env lost a secret, before pulling", async () => {
    await fs.writeFile(envFilePath(dir), "IMAGE_TAG=1.2.0\nSECRET_KEY=only-one\n");
    await expect(updateCommand(dir, { tag: "1.3.0" })).rejects.toThrow(/Restore it from backup/);
    expect(mocks.compose).not.toHaveBeenCalled();
    expect(await fs.readFile(envFilePath(dir), "utf8")).toBe("IMAGE_TAG=1.2.0\nSECRET_KEY=only-one\n");
  });

  it("does not restart when the pull fails", async () => {
    mocks.compose.mockResolvedValue({ code: 1, stdout: "", stderr: "" });
    await updateCommand(dir, {});
    expect(process.exitCode).toBe(1);
    expect(composeArgs()).toEqual([["-p", "bodhiorchard", "pull"]]);
  });

  it("switches a legacy install over to the renamed images", async () => {
    await fs.writeFile(
      composeFilePath(dir),
      "services:\n  backend:\n    image: mickyarun/bodhiorchard-backend:${IMAGE_TAG}\n",
    );
    await updateCommand(dir, {});
    const compose = await fs.readFile(composeFilePath(dir), "utf8");
    expect(compose).not.toContain("bodhiorchard-backend");
    expect(compose).toContain("mickyarun/glideship-backend:${IMAGE_TAG}");
  });
});
