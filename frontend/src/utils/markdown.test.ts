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

import { describe, it, expect, vi } from 'vitest'

// DOMPurify needs a real DOM (window.document) and the vitest config
// runs tests in the Node environment. We mock the sanitize call to
// identity so the test focuses on the marked rewrite contract — the
// rewrite is the part that's load-bearing for Mermaid; DOMPurify's
// own behaviour is upstream-tested and stable.
vi.mock('dompurify', () => ({
  default: {
    sanitize: (raw: string): string => raw,
  },
}))

import { renderMarkdown } from './markdown'

describe('renderMarkdown', () => {
  // The mermaid code-block contract is load-bearing: the tech-planner
  // skill emits ```mermaid``` blocks in tech specs, and the rendered
  // HTML must surface them as ``<pre class="mermaid">`` so the
  // useMermaidRender composable can find + render them on mount.

  it('rewrites mermaid fenced code blocks to <pre class="mermaid">', () => {
    const md = '```mermaid\nflowchart TD\n  A --> B\n```'
    const out = renderMarkdown(md)
    expect(out).toContain('<pre class="mermaid">')
    // Mermaid source must survive verbatim — arrows, brackets, the
    // whole DSL goes into the textContent that mermaid.run() will
    // parse. We don't assert exact whitespace because marked may
    // trim trailing newlines.
    expect(out).toContain('flowchart TD')
    expect(out).toContain('A --> B')
  })

  it('does not wrap mermaid blocks in <code> (mermaid.run reads textContent)', () => {
    // The default marked renderer emits ``<pre><code class="language-mermaid">``
    // which mermaid.js cannot auto-discover and which double-escapes
    // the arrow syntax. The custom renderer must bypass that wrapper.
    const out = renderMarkdown('```mermaid\ngraph LR\n```')
    expect(out).not.toContain('<code class="language-mermaid"')
  })

  it('leaves non-mermaid code blocks alone', () => {
    // Defence against the renderer accidentally swallowing every
    // fenced block. Other languages must still go through marked's
    // default ``<pre><code class="language-X">`` path so syntax
    // highlighting (if/when added) keeps working.
    const out = renderMarkdown('```python\nprint("hi")\n```')
    expect(out).toContain('<pre>')
    expect(out).toContain('<code class="language-python">')
    expect(out).not.toContain('<pre class="mermaid">')
  })

  it('returns empty string for null / undefined / empty input', () => {
    expect(renderMarkdown(null)).toBe('')
    expect(renderMarkdown(undefined)).toBe('')
    expect(renderMarkdown('')).toBe('')
  })

  it('preserves arrow syntax inside mermaid blocks (no HTML-escape)', () => {
    // Mermaid's flow syntax uses ``-->`` and ``-->|label|`` heavily.
    // If marked HTML-escapes the text into ``--&gt;``, mermaid.run()
    // cannot parse the diagram. The custom renderer passes ``token.text``
    // verbatim to keep the DSL intact.
    const md = '```mermaid\nA -->|yes| B\n```'
    const out = renderMarkdown(md)
    expect(out).toContain('-->|yes|')
    expect(out).not.toContain('--&gt;')
  })
})
