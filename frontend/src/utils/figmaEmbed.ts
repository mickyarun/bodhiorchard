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
 * Convert a Figma share URL into the canonical embed-host URL.
 *
 * Figma's embed API uses ``https://embed.figma.com`` (not ``www.``) and
 * mirrors the path shape of the share URL — ``/file/`` /
 * ``/design/`` / ``/proto/`` — with an additional ``embed-host`` query
 * param identifying the embedding application. When a ``node-id`` is
 * present in the source URL we forward it so the iframe deep-links
 * straight to the focused frame instead of dumping the whole file at
 * the user.
 *
 * Returns ``null`` on any unrecognised input so the Design tab can
 * render an inline parse-error callout rather than feeding a broken
 * URL to an iframe.
 *
 * Reference shapes accepted:
 *   https://www.figma.com/design/<KEY>/<name>?node-id=29471-2639
 *   https://figma.com/file/<KEY>/<name>
 *   https://www.figma.com/proto/<KEY>/<name>?starting-point-node-id=1-2
 */

// Captures the URL shape and the file key. Any ``www.`` is optional;
// ``figma.com/(file|design|proto)/<key>`` is mandatory. We anchor with
// ``^`` so a string that just happens to contain the pattern (e.g. a
// chat log) cannot slip through.
const FIGMA_URL_PATTERN = /^https:\/\/(?:www\.)?figma\.com\/(file|design|proto)\/([A-Za-z0-9]+)(?:\/[^?]*)?(?:\?(.*))?$/

const EMBED_HOST = 'bodhiorchard'

export function toEmbedUrl(rawUrl: string | null | undefined): string | null {
  if (!rawUrl) return null
  const trimmed = rawUrl.trim()
  if (!trimmed) return null
  const match = trimmed.match(FIGMA_URL_PATTERN)
  if (!match) return null

  const [, kind, fileKey, queryString] = match
  // Forward an explicit ``node-id`` so the iframe deep-links to the
  // focused frame. We deliberately do NOT forward arbitrary other query
  // params — Figma's embed accepts a specific set and a stray param
  // can cause Figma to silently 4xx the embed handshake.
  const params = new URLSearchParams({ 'embed-host': EMBED_HOST })
  if (queryString) {
    const sourceParams = new URLSearchParams(queryString)
    const nodeId = sourceParams.get('node-id')
    if (nodeId) params.set('node-id', nodeId)
  }
  return `https://embed.figma.com/${kind}/${fileKey}?${params.toString()}`
}
