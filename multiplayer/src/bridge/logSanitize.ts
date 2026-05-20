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
 * Strips every newline form a logger might honour: CR, LF, NEL,
 * line separator, paragraph separator. Caps length first so a
 * hostile gigabyte-sized name can't blow up the process. ``null``
 * and ``undefined`` are surfaced as literal placeholders so a
 * missing-field bug stays diagnosable in the log.
 */
// Matches CR (\r), LF (\n), NEL (U+0085), LS (U+2028), PS (U+2029).
// Built from a string so this source file itself contains no
// line-break characters that a static analyzer might confuse with
// real newlines.
const _NEWLINE_CHARS =
  "\\x0D\\x0A\\u0085\\u2028\\u2029"
const _NEWLINE_RE = new RegExp(`[${_NEWLINE_CHARS}]`, "g")

export function safeLog(value: unknown): string {
  if (value === null) return "<null>"
  if (value === undefined) return "<undefined>"
  const s = typeof value === "string" ? value : String(value)
  return s.slice(0, 500).replace(_NEWLINE_RE, "?")
}
