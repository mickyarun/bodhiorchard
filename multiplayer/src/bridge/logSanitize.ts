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

/** Line breaks that ``JSON.stringify`` does not escape. */
const UNICODE_LINE_BREAKS = /[\u0085\u2028\u2029]/g
/** Longest value ``safeLog`` keeps by default. */
const DEFAULT_MAX_LENGTH = 500
/** Longest error ``safeError`` keeps: room for a message and a useful stack. */
const ERROR_MAX_LENGTH = 2_000

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
 * ``\n``, ``\r`` and the other C0 control characters plus quotes and
 * backslashes. It leaves NEL (U+0085) and the Unicode line and paragraph
 * separators (U+2028, U+2029) as-is, and some log viewers break lines on
 * them, so those three are escaped explicitly afterwards. The
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
export function safeLog(value: unknown, maxLength = DEFAULT_MAX_LENGTH): string {
  if (value === null) return "<null>"
  if (value === undefined) return "<undefined>"
  const s = typeof value === "string" ? value : String(value)
  const capped = s.slice(0, maxLength)
  // JSON.stringify on a string returns ``"..."`` with embedded
  // escapes — strip the outer quotes for inline log readability.
  const escaped = JSON.stringify(capped).replace(UNICODE_LINE_BREAKS, (ch) =>
    `\\u${ch.charCodeAt(0).toString(16).padStart(4, "0")}`,
  )
  return escaped.slice(1, -1)
}

/**
 * A caught error as one sanitised log field: its stack (which starts with
 * the name and message), or the value itself when something other than an
 * Error was thrown. Error messages are not trusted text: a failed JSON parse
 * quotes the backend's body, a network error can quote a URL. Pass the result
 * as an argument to a constant format string, never as the format itself.
 */
export function safeError(err: unknown): string {
  if (err instanceof Error) return safeLog(err.stack ?? `${err.name}: ${err.message}`, ERROR_MAX_LENGTH)
  return safeLog(err, ERROR_MAX_LENGTH)
}
