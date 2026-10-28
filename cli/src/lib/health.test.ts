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

// waitForHealth: readiness needs a healthy backend AND a serving frontend.
// fetch is stubbed and timers are faked, so no network and no real waiting.
import { describe, it, expect, beforeEach, afterEach, vi } from "vitest";
import { waitForHealth } from "./health.js";

const fetchMock = vi.fn();

function routes(backend: () => Response | Promise<Response>, frontend: () => Response) {
  fetchMock.mockImplementation(async (url: string) => {
    if (url.endsWith("/health/")) return backend();
    return frontend();
  });
}

const healthy = (): Response => Response.json({ status: "ok" });
const serving = (): Response => new Response("<html></html>", { status: 200 });

beforeEach(() => {
  vi.useFakeTimers();
  fetchMock.mockReset();
  vi.stubGlobal("fetch", fetchMock);
});

afterEach(() => {
  vi.useRealTimers();
  vi.unstubAllGlobals();
});

describe("waitForHealth", () => {
  it("is ready as soon as both services answer", async () => {
    routes(healthy, serving);
    await expect(waitForHealth(8001, 3001)).resolves.toBe(true);
    const urls = fetchMock.mock.calls.map(([url]) => url);
    expect(urls).toEqual(["http://127.0.0.1:8001/health/", "http://127.0.0.1:3001/"]);
  });

  it("keeps polling until the backend reports ok", async () => {
    let calls = 0;
    routes(() => (++calls < 3 ? Response.json({ status: "starting" }) : healthy()), serving);
    const result = waitForHealth(8000, 3000, 60_000);
    await vi.advanceTimersByTimeAsync(10_000);
    await expect(result).resolves.toBe(true);
    expect(calls).toBe(3);
  });

  it("gives up after the timeout when the backend never becomes healthy", async () => {
    routes(() => new Response("bad gateway", { status: 502 }), serving);
    const result = waitForHealth(8000, 3000, 6_000);
    await vi.advanceTimersByTimeAsync(10_000);
    await expect(result).resolves.toBe(false);
  });

  it("is not ready while the frontend answers with a server error", async () => {
    routes(healthy, () => new Response("oops", { status: 503 }));
    const result = waitForHealth(8000, 3000, 4_000);
    await vi.advanceTimersByTimeAsync(5_000);
    await expect(result).resolves.toBe(false);
  });

  it("accepts a frontend 404 as serving", async () => {
    routes(healthy, () => new Response("not found", { status: 404 }));
    await expect(waitForHealth(8000, 3000)).resolves.toBe(true);
  });

  it("treats refused connections and non-JSON bodies as not ready", async () => {
    let calls = 0;
    routes(() => {
      calls += 1;
      if (calls === 1) throw new TypeError("fetch failed");
      if (calls === 2) return new Response("<html>proxy</html>", { status: 200 });
      return healthy();
    }, serving);
    const result = waitForHealth(8000, 3000, 60_000);
    await vi.advanceTimersByTimeAsync(10_000);
    await expect(result).resolves.toBe(true);
    expect(calls).toBe(3);
  });
});
