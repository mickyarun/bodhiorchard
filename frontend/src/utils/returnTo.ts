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
 * Where to go after signing in: the page someone was sent to login from.
 *
 * Kept in sessionStorage (this tab only) rather than a ``?redirect=`` on the
 * login URL, so a URL fragment survives (Slack status connect hands its code
 * over in one) and never ends up in a query string a server would log.
 */

const KEY = 'bodhiorchard_return_to'
/** Long enough to sign in (and pick an avatar); an abandoned one doesn't steer a later sign-in. */
const MAX_AGE_MS = 15 * 60 * 1000

/** Pages that make no sense to come back to after signing in. */
const NOT_A_DESTINATION = /^\/(login|setup|change-password)(?:[/?#]|$)/

/** An in-app path: one leading slash, so never another site (``//host``, ``/\host``). */
export function isSafeReturnPath(path: string): boolean {
  return /^\/(?![/\\])/.test(path) && !/[\u0000-\u001f]/.test(path) && !NOT_A_DESTINATION.test(path)
}

/**
 * Set once the session has run out and a full redirect to login is under way:
 * routing that still happens before the page unloads (a component tidying its
 * URL, say) must not replace the page it was really on. A reload resets it.
 */
let leaving = false

/**
 * Remember ``path`` (a route's ``fullPath``, fragment included) for after
 * sign-in. ``final`` is for the redirect that's leaving the page: what it
 * remembers stands until then.
 */
export function rememberReturnTo(path: string, { final = false } = {}): void {
  if (leaving || !isSafeReturnPath(path)) return
  leaving = final
  try {
    sessionStorage.setItem(KEY, JSON.stringify({ path, at: Date.now() }))
  } catch {
    // Storage blocked: they land on their home instead.
  }
}

/** The remembered path, once: it's forgotten as it's read. ``null`` if none, stale or unsafe. */
export function takeReturnTo(): string | null {
  try {
    const saved: unknown = JSON.parse(sessionStorage.getItem(KEY) ?? 'null')
    sessionStorage.removeItem(KEY)
    if (!saved || typeof saved !== 'object') return null
    const { path, at } = saved as { path?: unknown; at?: unknown }
    if (typeof path !== 'string' || typeof at !== 'number' || Date.now() - at > MAX_AGE_MS) return null
    return isSafeReturnPath(path) ? path : null
  } catch {
    return null
  }
}

/** Drop any remembered page (on logout). */
export function forgetReturnTo(): void {
  leaving = false
  try {
    sessionStorage.removeItem(KEY)
  } catch {
    // Nothing to forget.
  }
}
