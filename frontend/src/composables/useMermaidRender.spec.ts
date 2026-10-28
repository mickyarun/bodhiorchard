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
 * The tech spec's diagrams: quoted labels are fixed before drawing, and a
 * diagram that still doesn't parse shows its source instead of Mermaid's
 * error graphic. Mermaid's parser runs for real; drawing (``run``) is
 * stubbed because jsdom can't lay out SVG.
 */

import { flushPromises, mount } from '@vue/test-utils'
import mermaid from 'mermaid'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { defineComponent, h, ref } from 'vue'

import { MERMAID_FALLBACK_NOTICE, useMermaidRender } from '@/composables/useMermaidRender'

function mountDiagram(source: string): HTMLElement {
  const Host = defineComponent({
    setup() {
      const root = ref<HTMLElement | null>(null)
      useMermaidRender(root)
      return () => h('div', { ref: root }, [h('pre', { class: 'mermaid' }, source)])
    },
  })
  return mount(Host).element as HTMLElement
}

afterEach(() => {
  vi.restoreAllMocks()
})

describe('useMermaidRender', () => {
  it('draws a label with quotes inside once it is quoted', async () => {
    const run = vi.spyOn(mermaid, 'run').mockResolvedValue()
    const root = mountDiagram('flowchart TD\n  J --> K[Show pill, "n of 3" count]')
    await vi.waitFor(() => expect(run).toHaveBeenCalledOnce())
    const block = root.querySelector('pre')!
    expect(block.textContent).toBe('flowchart TD\n  J --> K["Show pill, #quot;n of 3#quot; count"]')
    expect(root.querySelector('.mermaid-notice')).toBeNull()
  })

  it('draws a diagram that already parses exactly as written', async () => {
    const run = vi.spyOn(mermaid, 'run').mockResolvedValue()
    // Quoting is how authors escape brackets and pipes; never rewrite it.
    const source = 'flowchart TD\n  A["x|y"] -->|"ok"| B["a -- b"]'
    const root = mountDiagram(source)
    await vi.waitFor(() => expect(run).toHaveBeenCalledOnce())
    expect(root.querySelector('pre')!.textContent).toBe(source)
  })

  it('shows the source with a notice when the diagram still has a syntax error', async () => {
    const run = vi.spyOn(mermaid, 'run').mockResolvedValue()
    const source = 'flowchart TD\n  A --> --> B'
    const root = mountDiagram(source)
    await vi.waitFor(() => expect(root.querySelector('.mermaid-notice')).not.toBeNull())
    await flushPromises()
    const block = root.querySelector('pre')!
    expect(block.classList.contains('mermaid')).toBe(false)
    expect(block.textContent).toBe(source)
    expect(root.querySelectorAll('.mermaid-notice')).toHaveLength(1)
    expect(root.querySelector('.mermaid-notice')!.textContent).toBe(MERMAID_FALLBACK_NOTICE)
    expect(run).not.toHaveBeenCalled()
  })
})
