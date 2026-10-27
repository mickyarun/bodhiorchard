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
 * SensitiveValueRow keeps a value masked until someone with reveal rights
 * asks for it, shows it only for a while, and never holds a value that
 * arrives after the row has gone. `.spec.ts` for jsdom.
 */

import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { defineComponent, h } from 'vue'
import { flushPromises, mount } from '@vue/test-utils'

import SensitiveValueRow from '../SensitiveValueRow.vue'

const VBtn = defineComponent({
  inheritAttrs: false,
  setup(_, { attrs, slots }) {
    return () => h('button', { ...attrs, type: 'button' }, slots.default?.())
  },
})

const SET = { is_set: true, last4: '4321' }

function mountRow(props: Partial<InstanceType<typeof SensitiveValueRow>['$props']> = {}) {
  return mount(SensitiveValueRow, {
    global: { stubs: { 'v-btn': VBtn } },
    props: {
      label: 'Account number',
      value: SET,
      canReveal: true,
      reveal: vi.fn().mockResolvedValue({ value: '1234567894321' }),
      ...props,
    },
  })
}

const revealButton = (wrapper: ReturnType<typeof mountRow>) =>
  wrapper.find('[aria-label="Reveal Account number"]')

beforeEach(() => {
  vi.useFakeTimers()
})

afterEach(() => {
  vi.useRealTimers()
})

describe('SensitiveValueRow', () => {
  it('shows only the masked value until revealed', () => {
    const wrapper = mountRow()
    expect(wrapper.text()).toContain('•••• 4321')
    expect(wrapper.text()).not.toContain('1234567894321')
    expect(revealButton(wrapper).exists()).toBe(true)
  })

  it('offers no Reveal without the right, or when nothing is saved', () => {
    expect(revealButton(mountRow({ canReveal: false })).exists()).toBe(false)
    expect(revealButton(mountRow({ value: { is_set: false, last4: null } })).exists()).toBe(false)
  })

  it('reveals through the given call, then hides again on its own', async () => {
    const reveal = vi.fn().mockResolvedValue({ value: '1234567894321' })
    const wrapper = mountRow({ reveal })
    await revealButton(wrapper).trigger('click')
    await flushPromises()
    expect(reveal).toHaveBeenCalledTimes(1)
    expect(wrapper.text()).toContain('1234567894321')

    vi.advanceTimersByTime(30_000)
    await flushPromises()
    expect(wrapper.text()).not.toContain('1234567894321')
    expect(wrapper.text()).toContain('•••• 4321')
  })

  it('hides straight away on Hide', async () => {
    const wrapper = mountRow()
    await revealButton(wrapper).trigger('click')
    await flushPromises()
    await wrapper.find('[aria-label="Hide Account number"]').trigger('click')
    expect(wrapper.text()).not.toContain('1234567894321')
  })

  it('shows the error and keeps the value masked when the reveal fails', async () => {
    const wrapper = mountRow({ reveal: vi.fn().mockResolvedValue({ error: 'Not allowed.' }) })
    await revealButton(wrapper).trigger('click')
    await flushPromises()
    expect(wrapper.text()).toContain('Not allowed.')
    expect(wrapper.text()).toContain('•••• 4321')
  })
})
