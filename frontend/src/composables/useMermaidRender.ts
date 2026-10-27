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
 * Composable that renders any ``<pre class="mermaid">`` blocks inside a
 * given root element via the Mermaid library.
 *
 * Pairs with the markdown pipeline in ``@/utils/markdown.ts`` — the
 * pipeline rewrites Mermaid fenced code blocks (` ```mermaid `) into
 * ``<pre class="mermaid">…</pre>`` placeholders during HTML
 * generation; this composable transforms those placeholders into
 * rendered SVG diagrams once the markup is in the DOM.
 *
 * Why a composable instead of an HTML post-processor: Mermaid's
 * ``run()`` mutates the DOM in place (replaces ``<pre>`` content with
 * SVG) and requires the elements to be actually mounted. Trying to
 * do this in a string-rendering step like ``renderMarkdown()`` would
 * either need a headless DOM (heavy) or produce stale output that
 * never re-renders when the source changes.
 */

import mermaid from 'mermaid'
import { onMounted, onUpdated, type Ref } from 'vue'

import { quoteMermaidLabels } from '@/utils/mermaidLabels'

/** Shown above a diagram that still doesn't parse, in place of Mermaid's error graphic. */
export const MERMAID_FALLBACK_NOTICE =
  "This diagram has a syntax error, so it's shown as source."

// Single global init — Mermaid keeps its config on a module-level
// singleton; calling ``initialize`` twice prints a warning. The flag
// guards against repeated calls when multiple composables mount.
let _initialized = false

function ensureInitialized(): void {
  if (_initialized) return
  mermaid.initialize({
    startOnLoad: false, // we run it manually per-mount
    securityLevel: 'strict', // disallow embedded HTML / click handlers
    // The app's Vuetify default theme is ``bodhiorchardDark``
    // (see src/plugins/vuetify.ts). Mermaid's ``default`` theme uses
    // dark edge colours that disappear against our dark surface;
    // ``dark`` switches the entire palette (light edges, lighter
    // node fills, white-on-dark text) and stays legible. If/when the
    // app adds a runtime light-mode toggle, lift this into a
    // reactive ``useTheme()`` lookup and re-init on change — for
    // now the static dark theme matches the static dark UI.
    theme: 'dark',
    flowchart: {
      htmlLabels: false, // render labels as SVG text, not foreign HTML
      curve: 'basis',
    },
  })
  _initialized = true
}

// Blocks a pass has started on.
const claimed = new WeakSet<HTMLElement>()

/**
 * Turn a block that can't be drawn back into a plain code block holding
 * its source, with a one-line notice above it. Dropping the ``mermaid``
 * class keeps later passes from trying it again.
 */
function showSource(node: HTMLElement, source: string): void {
  node.classList.remove('mermaid')
  node.classList.add('mermaid-source')
  node.textContent = source
  const notice = document.createElement('p')
  notice.className = 'mermaid-notice'
  notice.textContent = MERMAID_FALLBACK_NOTICE
  node.before(notice)
}

/** ``source`` if it parses, else its labels quoted if that parses, else null. */
async function parseable(source: string): Promise<string | null> {
  if (await mermaid.parse(source, { suppressErrors: true })) return source
  // Stray quotes in labels are a common slip in generated specs.
  const repaired = quoteMermaidLabels(source)
  if (repaired === source) return null
  return (await mermaid.parse(repaired, { suppressErrors: true })) ? repaired : null
}

/**
 * Draw one block. A diagram that doesn't parse, even with its labels
 * quoted, is shown as source rather than as Mermaid's error graphic.
 */
async function renderOne(node: HTMLElement): Promise<void> {
  // A mount and an update can both reach a block while it is still being parsed.
  if (claimed.has(node)) return
  claimed.add(node)
  const source = node.textContent ?? ''
  const drawable = await parseable(source)
  if (drawable === null) {
    showSource(node, source)
    return
  }
  node.textContent = drawable
  try {
    await mermaid.run({ nodes: [node] })
  } catch {
    showSource(node, source)
  }
}

/**
 * Find every ``.mermaid`` block inside ``rootRef.value`` and replace
 * its textContent with the rendered SVG. Each block is drawn on its
 * own, so one bad diagram doesn't blank the rest of the spec.
 */
export function useMermaidRender(rootRef: Ref<HTMLElement | null>): void {
  const runOnce = async (): Promise<void> => {
    if (!rootRef.value) return
    const nodes = Array.from(
      rootRef.value.querySelectorAll<HTMLElement>('pre.mermaid'),
    )
    if (nodes.length === 0) return
    ensureInitialized()
    // Mermaid replays diagrams in place. We filter to nodes that
    // haven't been processed yet (it stamps ``data-processed="true"``
    // after success) so successive ``onUpdated`` calls don't trigger
    // a re-render of every diagram on every keystroke in a sibling
    // editor.
    const pending = nodes.filter((n) => n.dataset.processed !== 'true')
    for (const node of pending) await renderOne(node)
  }

  onMounted(runOnce)
  onUpdated(runOnce)
}
