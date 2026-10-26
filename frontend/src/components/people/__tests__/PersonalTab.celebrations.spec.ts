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
 * The celebration opt-out on a profile belongs to the employee: they can
 * switch it either way; HR can only mute; nobody else can touch it. The UI
 * mirrors the API so HR is never offered an unmute the server would refuse.
 * `.spec.ts` for jsdom.
 */

import { beforeEach, describe, expect, it, vi } from 'vitest'
import { defineComponent, h } from 'vue'
import { flushPromises, mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'

const apiPatch = vi.fn()
vi.mock('@/services/api', () => ({ default: { patch: apiPatch, put: vi.fn(), get: vi.fn() } }))

const { default: PersonalTab } = await import('../PersonalTab.vue')

const VSwitch = defineComponent({
  inheritAttrs: false,
  props: ['label', 'disabled', 'hint', 'modelValue'],
  emits: ['update:modelValue'],
  setup(props, { emit }) {
    return () =>
      h('input', {
        type: 'checkbox',
        'data-field': props.label,
        'data-hint': props.hint ?? '',
        checked: !!props.modelValue,
        disabled: !!props.disabled,
        onChange: (e: Event) => emit('update:modelValue', (e.target as HTMLInputElement).checked),
      })
  },
})

const passthrough = defineComponent({
  inheritAttrs: false,
  setup(_, { slots }) {
    return () => h('div', slots.default?.())
  },
})

const STUBS = {
  'v-switch': VSwitch,
  'v-btn': passthrough,
  'v-form': passthrough,
  'v-text-field': passthrough,
  'v-select': passthrough,
  AppCallout: passthrough,
  FieldGrid: passthrough,
}

const PERSONAL = {
  phone: null,
  personal_email: null,
  emergency_contact_name: 'Someone',
  emergency_contact_relation: null,
  emergency_contact_phone: null,
  date_of_birth: '1990-10-22',
  gender: null,
  blood_group: null,
  celebrate_birthday: false, // muted
  celebrate_anniversary: true,
}

function mountTab(mode: 'hr' | 'self' | 'view', isSelf: boolean) {
  return mount(PersonalTab, {
    global: { stubs: STUBS },
    props: { employeeId: 'emp-1', personal: PERSONAL, mode, isSelf },
  })
}

const switchFor = (wrapper: ReturnType<typeof mount>, label: string) =>
  wrapper.find(`[data-field="${label}"]`)

beforeEach(() => {
  setActivePinia(createPinia())
  apiPatch.mockReset()
})

describe('PersonalTab celebration opt-outs', () => {
  it('lets the employee switch either one, both ways', () => {
    const wrapper = mountTab('self', true)
    expect(switchFor(wrapper, 'Announce my birthday').attributes('disabled')).toBeUndefined()
    expect(
      switchFor(wrapper, 'Announce my work anniversary').attributes('disabled'),
    ).toBeUndefined()
  })

  it('lets HR mute, but not unmute, someone else', () => {
    const wrapper = mountTab('hr', false)
    const birthday = switchFor(wrapper, 'Announce birthday') // currently muted
    expect(birthday.attributes('disabled')).toBeDefined()
    expect(birthday.attributes('data-hint')).toContain('Only they can turn it back on')
    expect(switchFor(wrapper, 'Announce work anniversary').attributes('disabled')).toBeUndefined()
  })

  it('gives a read-only viewer no switch to change', () => {
    const wrapper = mountTab('view', false)
    expect(switchFor(wrapper, 'Announce birthday').attributes('disabled')).toBeDefined()
    expect(switchFor(wrapper, 'Announce work anniversary').attributes('disabled')).toBeDefined()
  })

  it('saves a change straight away through the celebrations endpoint', async () => {
    apiPatch.mockResolvedValue({ data: {} })
    const wrapper = mountTab('self', true)
    const birthday = switchFor(wrapper, 'Announce my birthday')
    ;(birthday.element as HTMLInputElement).checked = true
    await birthday.trigger('change')
    await flushPromises()
    expect(apiPatch).toHaveBeenCalledWith('/v1/employees/emp-1/celebrations', {
      celebrate_birthday: true,
    })
  })
})
