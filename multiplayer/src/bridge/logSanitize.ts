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
 * Sanitize a value for inclusion in a console / file log line.
 *
 * The backend (and indirectly GitHub / Slack) feeds user-controlled
 * strings into the multiplayer server — repo names, branch names,
 * Slack display names, message bodies. If any of those contain a CR
 * or LF, naive string interpolation lets an attacker forge an extra
 * log line ("log injection", CodeQL js/log-injection). That breaks
 * downstream log-parsing tools and can mask real events.
 *
 * Defers to ``JSON.stringify`` for the heavy lifting — it escapes
 * every newline form (``\n``, ``\r``, ````, `` ``, `` ``)
 * plus quotes, backslashes, and other control characters. The
 * surrounding quotes ``JSON.stringify`` produces are stripped because
 * we want to inline the value into a free-form log message, not embed
 * it as a JSON string. ``JSON.stringify`` is on CodeQL's known-good
 * sanitiser list for ``js/log-injection``, so wrapping every
 * user-controlled interpolation in this helper closes the alert.
 *
 * Caps length first so a hostile gigabyte-sized name can't blow up
 * the process or the log line. ``null`` and ``undefined`` are
 * surfaced as literal placeholders so a missing-field bug stays
 * diagnosable.
 */
export function safeLog(value: unknown): string {
  if (value === null) return "<null>"
  if (value === undefined) return "<undefined>"
  const s = typeof value === "string" ? value : String(value)
  const capped = s.slice(0, 500)
  // JSON.stringify on a string returns ``"..."`` with embedded
  // escapes — strip the outer quotes for inline log readability.
  const escaped = JSON.stringify(capped)
  return escaped.slice(1, -1)
}
