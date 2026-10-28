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
 * A stand-in for the backend's bridge routes, for tests that run the real
 * matchmaker. `memberToken(userId, orgId)` verifies as that user in that org;
 * the org snapshot is empty and every other bridge call succeeds.
 */
import type { Mock } from "vitest"

const TOKEN_PREFIX = "jwt"

/** A token the stub backend verifies as `userId`, a member of `orgId`. */
export function memberToken(userId: string, orgId: string): string {
  return [TOKEN_PREFIX, userId, orgId].join(":")
}

/** Answer verify-token from `memberToken`, the org snapshot empty, the rest `{}`. */
export function stubBackend(fetchMock: Mock): void {
  fetchMock.mockImplementation(async (url: string, init?: RequestInit) => {
    const path = String(url)
    if (path.endsWith("/verify-token")) {
      const { token } = JSON.parse(String(init?.body)) as { token: string }
      const [prefix, userId, orgId] = token.split(":")
      if (prefix !== TOKEN_PREFIX) return Response.json({ valid: false })
      return Response.json({ valid: true, user_id: userId, org_id: orgId, name: userId })
    }
    if (path.includes("/org-snapshot/")) return Response.json({ members: [], repos: [] })
    return Response.json({})
  })
}

/** The bridge paths `fetchMock` was called with, in order. */
export function backendPaths(fetchMock: Mock): string[] {
  return fetchMock.mock.calls.map(([url]) => new URL(String(url)).pathname)
}
