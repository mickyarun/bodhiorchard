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

// Preflight: every command starts here, so each failure mode must name its fix.
import { describe, it, expect, beforeEach, vi } from "vitest";

const { dockerMock, resolveComposeMock } = vi.hoisted(() => ({
  dockerMock: vi.fn(),
  resolveComposeMock: vi.fn(),
}));
vi.mock("./docker.js", () => ({ docker: dockerMock, resolveComposeCommand: resolveComposeMock }));

import { PreflightError, preflight } from "./preflight.js";

const ok = { code: 0, stdout: "", stderr: "" };
const failed = { code: 1, stdout: "", stderr: "Cannot connect to the Docker daemon" };

beforeEach(() => {
  dockerMock.mockReset();
  resolveComposeMock.mockReset();
  resolveComposeMock.mockResolvedValue(["docker", "compose"]);
});

describe("preflight", () => {
  it("passes when docker, the daemon and compose are all available", async () => {
    dockerMock.mockResolvedValue(ok);
    await expect(preflight()).resolves.toBeUndefined();
    expect(dockerMock.mock.calls).toEqual([[["--version"]], [["info"]]]);
    expect(resolveComposeMock).toHaveBeenCalledTimes(1);
  });

  it("points at the Docker install guide when docker is missing", async () => {
    dockerMock.mockRejectedValue(new Error("Could not run `docker`"));
    const err = await preflight().catch((e: unknown) => e);
    expect(err).toBeInstanceOf(PreflightError);
    expect((err as Error).message).toMatch(/not installed or not on PATH/);
    expect((err as Error).message).toContain("https://docs.docker.com/get-docker/");
  });

  it("treats a non-zero `docker --version` as missing docker", async () => {
    dockerMock.mockResolvedValue(failed);
    await expect(preflight()).rejects.toThrow(/not installed or not on PATH/);
  });

  it("asks the user to start the daemon when `docker info` fails", async () => {
    dockerMock.mockResolvedValueOnce(ok).mockResolvedValueOnce(failed);
    const err = await preflight().catch((e: unknown) => e);
    expect(err).toBeInstanceOf(PreflightError);
    expect((err as Error).message).toMatch(/daemon isn't running/);
    expect(resolveComposeMock).not.toHaveBeenCalled();
  });

  it("propagates a missing compose error", async () => {
    dockerMock.mockResolvedValue(ok);
    resolveComposeMock.mockRejectedValue(new Error("Docker Compose is not available."));
    await expect(preflight()).rejects.toThrow("Docker Compose is not available.");
  });
});
