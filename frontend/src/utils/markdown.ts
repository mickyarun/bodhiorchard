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

import { marked } from 'marked'
import DOMPurify from 'dompurify'

// Custom code-block renderer: when the language hint is ``mermaid``,
// emit ``<pre class="mermaid">`` with the raw source instead of the
// default ``<pre><code class="language-mermaid">``. The Mermaid
// library (``mermaid.run()``) auto-discovers any ``.mermaid``
// element on the page and replaces its textContent with the
// rendered SVG diagram. ``token.text`` is the raw fenced source —
// marked exposes the un-escaped string for code tokens so the
// arrow syntax (``-->``, ``-->|label|``) survives intact for the
// Mermaid parser; no manual decoding is required.
//
// All other languages fall through to ``marked``'s default code-block
// renderer (which preserves syntax highlighting hooks via the
// ``language-<lang>`` class).
const renderer = new marked.Renderer()
const defaultCodeRenderer = renderer.code.bind(renderer)
renderer.code = (token) => {
  if (token.lang === 'mermaid') {
    // ``token.text`` is the raw fenced-block source. We pass it
    // through verbatim — Mermaid expects its own DSL, not HTML.
    return `<pre class="mermaid">${token.text}</pre>\n`
  }
  return defaultCodeRenderer(token)
}

marked.use({ renderer })

// DOMPurify by default strips data-* attributes some Mermaid versions
// add; keep ``class`` on ``<pre>`` so ``.mermaid`` survives sanitisation.
// We add ``svg`` + its attributes to the allow-list too because after
// ``mermaid.run()`` replaces the ``<pre>`` content with an SVG, a
// subsequent ``renderMarkdown()`` round-trip on edited content would
// otherwise drop the rendered output. (Today we don't round-trip, but
// keeping the policy explicit prevents future regressions.)
const SANITIZE_CONFIG = {
  ADD_TAGS: ['svg', 'g', 'path', 'rect', 'circle', 'line', 'text', 'tspan', 'marker', 'defs'],
  ADD_ATTR: ['viewBox', 'd', 'fill', 'stroke', 'transform', 'marker-end', 'marker-start'],
}

export function renderMarkdown(md: string | null | undefined): string {
  if (!md) return ''
  const raw = marked.parse(md, { async: false }) as string
  return DOMPurify.sanitize(raw, SANITIZE_CONFIG)
}
