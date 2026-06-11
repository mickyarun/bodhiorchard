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

import { describe, it, expect } from 'vitest'
import { mount } from '@vue/test-utils'
import MemberPicker, { type MemberPickerEntry } from '../MemberPicker.vue'

// Vuetify components inside MemberPicker (only ``<v-icon>`` and
// ``<v-progress-circular>``) need the global ``v-`` prefix to be tolerated
// when no Vuetify plugin is registered. ``stubs`` keeps them inert.
const VUETIFY_STUBS = {
  'v-icon': true,
  'v-progress-circular': true,
}

const ALICE: MemberPickerEntry = { id: 'a', name: 'Alice', email: 'alice@x.io' }
const BOB: MemberPickerEntry = { id: 'b', name: 'Bob', email: 'bob@x.io' }
const CHRIS: MemberPickerEntry = { id: 'c', name: 'Chris', email: 'chris@x.io' }

describe('MemberPicker', () => {
  it('renders a row per member with name and email', () => {
    const wrapper = mount(MemberPicker, {
      global: { stubs: VUETIFY_STUBS },
      props: { members: [ALICE, BOB], modelValue: [], maxSelection: 2 },
    })
    const rows = wrapper.findAll('.member-picker__item')
    expect(rows).toHaveLength(2)
    expect(rows[0].text()).toContain('Alice')
    expect(rows[0].text()).toContain('alice@x.io')
    expect(rows[1].text()).toContain('Bob')
  })

  it('emits update:modelValue with the selected id on click', async () => {
    const wrapper = mount(MemberPicker, {
      global: { stubs: VUETIFY_STUBS },
      props: { members: [ALICE, BOB], modelValue: [], maxSelection: 2 },
    })
    await wrapper.findAll('.member-picker__item')[0].trigger('click')

    const emitted = wrapper.emitted('update:modelValue')
    expect(emitted).toBeTruthy()
    expect(emitted![0]).toEqual([['a']])
  })

  it('toggles a selected id off when clicked again', async () => {
    const wrapper = mount(MemberPicker, {
      global: { stubs: VUETIFY_STUBS },
      props: { members: [ALICE, BOB], modelValue: ['a'], maxSelection: 2 },
    })
    await wrapper.findAll('.member-picker__item')[0].trigger('click')

    expect(wrapper.emitted('update:modelValue')![0]).toEqual([[]])
  })

  it('disables un-selected rows once maxSelection is reached', async () => {
    const wrapper = mount(MemberPicker, {
      global: { stubs: VUETIFY_STUBS },
      props: { members: [ALICE, BOB, CHRIS], modelValue: ['a'], maxSelection: 1 },
    })
    const rows = wrapper.findAll('.member-picker__item')

    // Alice is already selected — not disabled (so the user can de-select).
    expect(rows[0].classes()).not.toContain('member-picker__item--disabled')
    expect((rows[0].element as HTMLButtonElement).disabled).toBe(false)

    // Bob and Chris are at the cap and not selected — disabled.
    expect(rows[1].classes()).toContain('member-picker__item--disabled')
    expect((rows[1].element as HTMLButtonElement).disabled).toBe(true)
    expect(rows[2].classes()).toContain('member-picker__item--disabled')
    expect((rows[2].element as HTMLButtonElement).disabled).toBe(true)
  })

  it('refuses to push beyond maxSelection from the parent contract', async () => {
    // Defence in depth: even if a caller passes a modelValue at the cap and
    // the user races a click on an enabled-but-not-yet-disabled row, the
    // toggle helper short-circuits without emitting a too-long array.
    const wrapper = mount(MemberPicker, {
      global: { stubs: VUETIFY_STUBS },
      props: { members: [ALICE, BOB], modelValue: ['a'], maxSelection: 1 },
    })
    // Trigger click on the (disabled) Bob row anyway via JS to bypass the
    // browser-level disabled guard.
    const bobButton = wrapper.findAll('.member-picker__item')[1]
    await bobButton.trigger('click')

    expect(wrapper.emitted('update:modelValue')).toBeFalsy()
  })

  it('shows the empty message when members is empty (and not loading)', () => {
    const wrapper = mount(MemberPicker, {
      global: { stubs: VUETIFY_STUBS },
      props: {
        members: [],
        modelValue: [],
        maxSelection: 2,
        emptyMessage: 'Nobody to invite yet.',
      },
    })
    expect(wrapper.find('.member-picker__empty').text()).toBe('Nobody to invite yet.')
    expect(wrapper.find('.member-picker__list').exists()).toBe(false)
  })

  it('shows the spinner while loading even if members are empty', () => {
    const wrapper = mount(MemberPicker, {
      global: { stubs: VUETIFY_STUBS },
      props: { members: [], modelValue: [], maxSelection: 2, loading: true },
    })
    expect(wrapper.find('.member-picker__empty').exists()).toBe(false)
    expect(wrapper.find('v-progress-circular-stub').exists()).toBe(true)
  })
})
