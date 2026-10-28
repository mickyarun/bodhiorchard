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

// Compose detection without the v2 plugin. The resolved prefix is cached per
// module, so this file owns a fresh module instance: first it proves a host
// with no Compose at all is refused (and not cached), then that the legacy
// `docker-compose` binary is picked up once it appears.
import { EventEmitter } from "node:events";
import { describe, it, expect, vi } from "vitest";

const { spawnMock } = vi.hoisted(() => ({ spawnMock: vi.fn() }));
vi.mock("node:child_process", () => ({ spawn: spawnMock }));

import { compose, resolveComposeCommand } from "./docker.js";

function answer(outcome: (cmd: string, args: string[]) => { code: number } | { error: string }) {
  spawnMock.mockImplementation((cmd: string, args: string[]) => {
    const child = Object.assign(new EventEmitter(), {
      stdout: new EventEmitter(),
      stderr: new EventEmitter(),
    });
    const result = outcome(cmd, args);
    setImmediate(() => {
      if ("error" in result) {
        child.emit("error", Object.assign(new Error("spawn failed"), { code: result.error }));
      } else {
        child.emit("close", result.code);
      }
    });
    return child;
  });
}

describe("compose detection without the v2 plugin", () => {
  it("refuses when no Compose exists, then picks up a later-installed docker-compose", async () => {
    answer((cmd) => (cmd === "docker" ? { code: 1 } : { error: "ENOENT" }));
    await expect(resolveComposeCommand()).rejects.toThrow(/Docker Compose is not available/);
    await expect(resolveComposeCommand()).rejects.toThrow(/Docker Compose is not available/);
    expect(spawnMock.mock.calls.filter(([cmd]) => cmd === "docker-compose")).toHaveLength(2);

    // The legacy binary is installed afterwards: the next probe finds it.
    answer((cmd) => (cmd === "docker" ? { code: 125 } : { code: 0 }));

    expect(await resolveComposeCommand()).toEqual(["docker-compose"]);
    await compose("/tmp/install", ["-p", "bodhiorchard", "ps"]);

    const last = spawnMock.mock.calls.at(-1);
    expect(last?.[0]).toBe("docker-compose");
    expect(last?.[1]).toEqual(["-p", "bodhiorchard", "ps"]);
  });
});
