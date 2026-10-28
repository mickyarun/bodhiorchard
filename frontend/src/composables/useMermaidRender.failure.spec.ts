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
 * A tech spec diagram that fails to draw: the source shows in its place
 * with one notice, the other diagrams on the page still draw, and a block
 * already drawn or already shown as source is never tried again. Mermaid's
 * parser runs for real; ``run`` is stubbed because jsdom can't lay out SVG.
 */
import { flushPromises, mount } from '@vue/test-utils'
import mermaid from 'mermaid'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { defineComponent, h, ref } from 'vue'

import { MERMAID_FALLBACK_NOTICE, useMermaidRender } from '@/composables/useMermaidRender'

const GOOD = 'flowchart TD\n  A --> B'
const BAD = 'flowchart TD\n  A --> --> B'

function mountBlocks(blocks: { source: string; processed?: boolean }[]) {
  const tick = ref(0)
  const Host = defineComponent({
    setup() {
      const root = ref<HTMLElement | null>(null)
      useMermaidRender(root)
      return () => h('div', { ref: root, 'data-tick': tick.value }, blocks.map(b =>
        h('pre', { class: 'mermaid', 'data-processed': b.processed ? 'true' : undefined }, b.source)))
    },
  })
  const wrapper = mount(Host)
  return { root: wrapper.element as HTMLElement, rerender: () => { tick.value++ } }
}

afterEach(() => vi.restoreAllMocks())

describe('useMermaidRender failures', () => {
  it('shows the source when drawing throws after a clean parse', async () => {
    const run = vi.spyOn(mermaid, 'run').mockRejectedValue(new Error('layout failed'))
    const { root } = mountBlocks([{ source: GOOD }])
    await vi.waitFor(() => expect(root.querySelector('.mermaid-notice')).not.toBeNull())
    const block = root.querySelector('pre')!
    expect(run).toHaveBeenCalledOnce()
    expect(block.classList.contains('mermaid-source')).toBe(true)
    expect(block.classList.contains('mermaid')).toBe(false)
    expect(block.textContent).toBe(GOOD)
    expect(root.querySelector('.mermaid-notice')!.textContent).toBe(MERMAID_FALLBACK_NOTICE)
  })

  it('still draws the good diagrams around a bad one', async () => {
    const run = vi.spyOn(mermaid, 'run').mockResolvedValue()
    const { root } = mountBlocks([{ source: GOOD }, { source: BAD }, { source: GOOD }])
    await vi.waitFor(() => expect(run).toHaveBeenCalledTimes(2))
    await flushPromises()
    const blocks = root.querySelectorAll('pre')
    expect(blocks[0].classList.contains('mermaid')).toBe(true)
    expect(blocks[1].classList.contains('mermaid-source')).toBe(true)
    expect(blocks[2].classList.contains('mermaid')).toBe(true)
    expect(root.querySelectorAll('.mermaid-notice')).toHaveLength(1)
  })

  it('does not retry a failed diagram on the next update', async () => {
    const run = vi.spyOn(mermaid, 'run').mockResolvedValue()
    const parse = vi.spyOn(mermaid, 'parse')
    const { root, rerender } = mountBlocks([{ source: BAD }])
    await vi.waitFor(() => expect(root.querySelector('.mermaid-notice')).not.toBeNull())
    const parsedOnce = parse.mock.calls.length
    rerender()
    await flushPromises()
    expect(parse.mock.calls.length).toBe(parsedOnce)
    expect(root.querySelectorAll('.mermaid-notice')).toHaveLength(1)
    expect(run).not.toHaveBeenCalled()
  })

  it('skips a diagram Mermaid has already drawn', async () => {
    const run = vi.spyOn(mermaid, 'run').mockResolvedValue()
    const parse = vi.spyOn(mermaid, 'parse')
    mountBlocks([{ source: GOOD, processed: true }])
    await flushPromises()
    expect(parse).not.toHaveBeenCalled()
    expect(run).not.toHaveBeenCalled()
  })
})
