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
 * Turn a stored `avatar_url` into something an `<img>` can load.
 *
 * Self-hosted photos are stored root-relative (`/api/v1/employees/avatars/…`)
 * so a domain change doesn't need a data migration. That resolves against
 * the *frontend's* origin — correct when the API sits behind the same origin
 * (the Vite proxy, Caddy), wrong for a split-host deployment where
 * `VITE_API_BASE_URL` points the SPA at another host. In that case the path
 * is rebased onto the API's origin. Absolute (Slack CDN) URLs pass through.
 *
 * @param avatarUrl - The stored value, or null.
 * @param apiBase - The configured API base; injectable for tests.
 */
export function resolveAvatarUrl(
  avatarUrl: string | null | undefined,
  apiBase: string = import.meta.env.VITE_API_BASE_URL ?? '',
): string | null {
  if (!avatarUrl) return null
  if (!avatarUrl.startsWith('/api/')) return avatarUrl
  if (!/^https?:\/\//.test(apiBase)) return avatarUrl
  // VITE_API_BASE_URL conventionally ends in "/api"; the stored path
  // already carries that prefix, so join on the origin only.
  return `${new URL(apiBase).origin}${avatarUrl}`
}

/**
 * Up to two initials for the monogram fallback, e.g. "Ada Lovelace" → "AL".
 * A trailing ellipsis (shortened ids like "38ca3fde…") is not part of the name.
 */
export function initialsOf(name: string): string {
  return (
    name
      .replace(/…$/, '')
      .split(/\s+/)
      .filter(Boolean)
      .map(part => part[0])
      .join('')
      .toUpperCase()
      .slice(0, 2) || '?'
  )
}
