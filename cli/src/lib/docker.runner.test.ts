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

// Docker runner with Compose v2 available: argument forwarding, stdio modes,
// output capture, prefix caching and spawn-error messages. `spawn` is faked.
import { EventEmitter } from "node:events";
import { describe, it, expect, beforeEach, vi } from "vitest";

const { spawnMock } = vi.hoisted(() => ({ spawnMock: vi.fn() }));
vi.mock("node:child_process", () => ({ spawn: spawnMock }));

import { compose, docker } from "./docker.js";

type Outcome = { code: number | null; stdout?: string; stderr?: string } | { error: string };

function answer(outcome: (cmd: string, args: string[]) => Outcome) {
  spawnMock.mockImplementation((cmd: string, args: string[], opts: { stdio: unknown }) => {
    const child = Object.assign(new EventEmitter(), {
      stdout: opts.stdio === "inherit" ? null : new EventEmitter(),
      stderr: opts.stdio === "inherit" ? null : new EventEmitter(),
    });
    const result = outcome(cmd, args);
    setImmediate(() => {
      if ("error" in result) {
        child.emit("error", Object.assign(new Error("spawn failed"), { code: result.error }));
        return;
      }
      if (result.stdout) child.stdout?.emit("data", Buffer.from(result.stdout));
      if (result.stderr) child.stderr?.emit("data", Buffer.from(result.stderr));
      child.emit("close", result.code);
    });
    return child;
  });
}

beforeEach(() => {
  spawnMock.mockReset();
  answer(() => ({ code: 0, stdout: "ok" }));
});

describe("docker()", () => {
  it("captures stdout, stderr and the exit code", async () => {
    answer(() => ({ code: 3, stdout: "out", stderr: "err" }));
    expect(await docker(["info"])).toEqual({ code: 3, stdout: "out", stderr: "err" });
    expect(spawnMock).toHaveBeenCalledWith(
      "docker",
      ["info"],
      expect.objectContaining({ stdio: ["ignore", "pipe", "pipe"], windowsHide: true }),
    );
  });

  it("reports a missing binary with an install hint instead of ENOENT", async () => {
    answer(() => ({ error: "ENOENT" }));
    await expect(docker(["--version"])).rejects.toThrow(
      "Could not run `docker` — is it installed and on your PATH?",
    );
  });

  it("passes other spawn errors through unchanged", async () => {
    answer(() => ({ error: "EACCES" }));
    await expect(docker(["info"])).rejects.toMatchObject({ code: "EACCES" });
  });

  it("treats a signal-killed child (null exit code) as a failure", async () => {
    answer(() => ({ code: null }));
    expect((await docker(["info"])).code).toBe(1);
  });
});

describe("compose() with the v2 plugin", () => {
  it("prefixes `docker compose`, runs in the project dir and caches the probe", async () => {
    const dir = "/tmp/glideship-install";
    await compose(dir, ["-p", "bodhiorchard", "ps"]);
    await compose(dir, ["-p", "bodhiorchard", "down"], { inherit: true });

    const probes = spawnMock.mock.calls.filter(([, args]) => args.join(" ") === "compose version");
    expect(probes).toHaveLength(1);
    const runs = spawnMock.mock.calls.filter(([, args]) => args[0] === "compose" && args[1] === "-p");
    expect(runs.map(([cmd, args]) => [cmd, ...args])).toEqual([
      ["docker", "compose", "-p", "bodhiorchard", "ps"],
      ["docker", "compose", "-p", "bodhiorchard", "down"],
    ]);
    expect(runs[0]?.[2]).toMatchObject({ cwd: dir, stdio: ["ignore", "pipe", "pipe"] });
    expect(runs[1]?.[2]).toMatchObject({ cwd: dir, stdio: "inherit" });
  });

  it("returns a failing compose exit code instead of throwing", async () => {
    answer((_cmd, args) => (args[1] === "-p" ? { code: 1, stderr: "port is allocated" } : { code: 0 }));
    const res = await compose("/tmp/x", ["-p", "bodhiorchard", "up", "-d"]);
    expect(res).toMatchObject({ code: 1, stderr: "port is allocated" });
  });
});
