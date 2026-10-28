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

/**
 * The org id becomes a path segment of the backend's snapshot URL, so it is
 * encoded: an id carrying `/`, `..`, `?` or `#` must not reach another route.
 */
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"
import { fetchOrgSnapshot } from "./BackendClient"
import { isUuid } from "./uuid"

const fetchMock = vi.fn()

function requestedPath(): string {
  const [url] = fetchMock.mock.calls[0] as [string]
  return new URL(url).pathname + new URL(url).search + new URL(url).hash
}

beforeEach(() => {
  fetchMock.mockReset()
  fetchMock.mockResolvedValue(Response.json({ orgId: "x", members: [], repos: [] }))
  vi.stubGlobal("fetch", fetchMock)
})

afterEach(() => {
  vi.unstubAllGlobals()
})

describe("fetchOrgSnapshot", () => {
  it("keeps the org id inside one encoded path segment", async () => {
    await fetchOrgSnapshot("../../users/me?admin=1#x")

    expect(requestedPath()).toBe(
      "/api/v1/internal/colyseus/org-snapshot/..%2F..%2Fusers%2Fme%3Fadmin%3D1%23x",
    )
  })

  it("leaves a UUID unchanged", async () => {
    const orgId = "0b4f4f53-58a4-4c55-9a0e-6f1c2b7d9e10"
    await fetchOrgSnapshot(orgId)

    expect(requestedPath()).toBe(`/api/v1/internal/colyseus/org-snapshot/${orgId}`)
  })
})

describe("isUuid", () => {
  it.each([
    ["0b4f4f53-58a4-4c55-9a0e-6f1c2b7d9e10", true],
    ["0B4F4F53-58A4-4C55-9A0E-6F1C2B7D9E10", true],
    ["0b4f4f5358a44c559a0e6f1c2b7d9e10", false],
    [" 0b4f4f53-58a4-4c55-9a0e-6f1c2b7d9e10", false],
    ["org-a", false],
    [42, false],
    [null, false],
  ])("%s -> %s", (value, expected) => {
    expect(isUuid(value)).toBe(expected)
  })
})
