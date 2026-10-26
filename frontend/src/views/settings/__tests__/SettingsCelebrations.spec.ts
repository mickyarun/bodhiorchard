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
 * Celebrations settings: HR tunes the schedule, admins/owner own the channel.
 *
 * Vuetify inputs are stubbed with elements that expose their `label`,
 * `disabled` and `hint` as data attributes, so these test the page's own
 * decisions rather than Vuetify's rendering. `.spec.ts` for jsdom.
 */

import { beforeEach, describe, expect, it, vi } from 'vitest'
import { defineComponent, h } from 'vue'
import { flushPromises, mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'

const apiGet = vi.fn()
vi.mock('@/services/api', () => ({ default: { get: apiGet, patch: vi.fn(), post: vi.fn() } }))

const { default: SettingsCelebrations } = await import('../SettingsCelebrations.vue')
const { useAuthStore } = await import('@/stores/auth')

const field = (tag: string) =>
  defineComponent({
    inheritAttrs: false,
    props: ['label', 'disabled', 'hint', 'modelValue', 'items', 'errorMessages'],
    setup(props, { slots }) {
      return () =>
        h(
          tag,
          {
            'data-field': props.label ?? '',
            'data-disabled': String(!!props.disabled),
            'data-hint': props.hint ?? '',
            'data-value': JSON.stringify(props.modelValue ?? null),
          },
          slots.default?.(),
        )
    },
  })

const slotted = (tag: string) =>
  defineComponent({
    inheritAttrs: false,
    setup(_, { slots }) {
      return () => h(tag, [slots.default?.(), slots['header-actions']?.(), slots.prepend?.()])
    },
  })

const STUBS = {
  SettingsPageShell: slotted('section'),
  AppCallout: slotted('aside'),
  'v-switch': field('div'),
  'v-text-field': field('div'),
  'v-select': field('div'),
  'v-autocomplete': field('div'),
  'v-combobox': field('div'),
  'v-btn': slotted('button'),
  'v-list': slotted('ul'),
  'v-list-item': slotted('li'),
  'v-list-item-title': slotted('span'),
  'v-list-item-subtitle': slotted('small'),
  'v-chip': slotted('em'),
}

const SAVED = {
  enabled: false,
  slackChannelId: null,
  postTime: '09:30',
  timezone: null,
  activeWeekdays: [0, 1, 2, 3, 4, 5, 6],
  weekendPolicy: 'roll_forward',
  includeBirthdays: true,
  includeAnniversaries: true,
  mentionChannel: false,
  gifEnabled: true,
  gifRating: 'g',
  gifTags: ['party'],
}

function respond(settings: object, history: object[] = []) {
  apiGet.mockImplementation((url: string) => {
    if (url.endsWith('/history')) return Promise.resolve({ data: history })
    if (url.endsWith('/audience')) return Promise.resolve({ data: { birthdays: 3, anniversaries: 4 } })
    return Promise.resolve({ data: settings })
  })
}

async function mountAs(permissions: string[]) {
  const auth = useAuthStore()
  auth.user = { id: 'me', permissions } as never
  const wrapper = mount(SettingsCelebrations, { global: { stubs: STUBS } })
  await flushPromises()
  return wrapper
}

const fieldEl = (wrapper: ReturnType<typeof mount>, label: string) =>
  wrapper.find(`[data-field="${label}"]`)

beforeEach(() => {
  setActivePinia(createPinia())
  apiGet.mockReset()
})

describe('SettingsCelebrations', () => {
  it('locks the channel and @channel ping for HR', async () => {
    respond(SAVED)
    const wrapper = await mountAs(['employees:manage'])
    for (const label of ['Slack channel ID', 'Ping @channel']) {
      expect(fieldEl(wrapper, label).attributes('data-disabled')).toBe('true')
      expect(fieldEl(wrapper, label).attributes('data-hint')).toContain('admin or the org owner')
    }
  })

  it('lets an admin edit the channel and @channel ping', async () => {
    respond(SAVED)
    const wrapper = await mountAs(['org:edit_settings'])
    expect(fieldEl(wrapper, 'Slack channel ID').attributes('data-disabled')).toBe('false')
    expect(fieldEl(wrapper, 'Ping @channel').attributes('data-disabled')).toBe('false')
  })

  it('tells HR why they cannot switch it on without a channel', async () => {
    respond({ ...SAVED, enabled: true })
    const wrapper = await mountAs(['employees:manage'])
    expect(wrapper.text()).toContain('needs to choose the Slack channel')
  })

  it('shows no such hint to an admin', async () => {
    respond({ ...SAVED, enabled: true })
    const wrapper = await mountAs(['org:edit_settings'])
    expect(wrapper.text()).not.toContain('needs to choose the Slack channel')
  })

  it('pre-fills the timezone from the browser when none is saved', async () => {
    respond(SAVED)
    const wrapper = await mountAs(['org:edit_settings'])
    const browser = Intl.DateTimeFormat().resolvedOptions().timeZone
    expect(JSON.parse(fieldEl(wrapper, 'Timezone').attributes('data-value')!)).toBe(browser)
  })

  it('keeps a saved timezone', async () => {
    respond({ ...SAVED, timezone: 'Asia/Kolkata' })
    const wrapper = await mountAs(['org:edit_settings'])
    expect(JSON.parse(fieldEl(wrapper, 'Timezone').attributes('data-value')!)).toBe('Asia/Kolkata')
  })

  it('hides the weekend policy on a seven-day schedule and shows it when narrowed', async () => {
    respond(SAVED)
    let wrapper = await mountAs(['org:edit_settings'])
    expect(fieldEl(wrapper, 'When a celebration falls on a non-posting day').exists()).toBe(false)

    setActivePinia(createPinia())
    respond({ ...SAVED, activeWeekdays: [0, 1, 2, 3, 4] })
    wrapper = await mountAs(['org:edit_settings'])
    expect(fieldEl(wrapper, 'When a celebration falls on a non-posting day').exists()).toBe(true)
  })

  it('lists recent posts with a plain-English status and reason', async () => {
    respond(SAVED, [
      {
        celebrate_date: '2026-10-22',
        status: 'failed',
        attempts: 3,
        birthday_count: 1,
        anniversary_count: 0,
        last_error: 'not_in_channel',
      },
      {
        celebrate_date: '2026-10-21',
        status: 'unknown',
        attempts: 1,
        birthday_count: 0,
        anniversary_count: 2,
        last_error: 'ReadTimeout',
      },
    ])
    const wrapper = await mountAs(['employees:manage'])
    const text = wrapper.text()
    expect(text).toContain('Failed')
    expect(text).toContain('The bot is not in that channel yet')
    expect(text).toContain('Unsure')
    expect(text).toContain('may or may not have reached Slack')
  })
})
