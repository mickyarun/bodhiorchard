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
 * The BUD detail page before the BUD shows: a skeleton while loading, or
 * the error with a way back to the board and a retry.
 */
import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'

import BUDDetailLoadState from '../BUDDetailLoadState.vue'

const stubs = {
  'v-skeleton-loader': { template: '<div class="skeleton" />' },
  'v-btn': {
    props: ['to'],
    emits: ['click'],
    template: '<button type="button" :data-to="to" @click="$emit(\'click\')"><slot /></button>',
  },
  AppCallout: {
    props: ['title'],
    template: '<div class="callout"><strong>{{ title }}</strong><slot /><slot name="actions" /></div>',
  },
}

function mountState(loading: boolean, error = '') {
  return mount(BUDDetailLoadState, { props: { loading, error }, global: { stubs } })
}

describe('BUDDetailLoadState', () => {
  it('shows the page shape while loading, and no error', () => {
    const wrapper = mountState(true, 'stale error')
    expect(wrapper.findAll('.skeleton').length).toBeGreaterThan(0)
    expect(wrapper.find('.callout').exists()).toBe(false)
  })

  it('shows the error with a way back and a retry', async () => {
    const wrapper = mountState(false, 'BUD not found')
    expect(wrapper.find('.skeleton').exists()).toBe(false)
    expect(wrapper.find('.callout').text()).toContain("This BUD didn't load")
    expect(wrapper.find('.callout').text()).toContain('BUD not found')

    const buttons = wrapper.findAll('button')
    expect(buttons.map(b => b.text())).toEqual(['Back to board', 'Retry'])
    expect(buttons[0].attributes('data-to')).toBe('/buds')
    await buttons[1].trigger('click')
    expect(wrapper.emitted('retry')).toHaveLength(1)
  })
})
