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
 * AI provider settings: Save and Test connection need integrations:configure,
 * the permission both backend routes require. The settings composable and
 * child inputs are stubbed, so this tests the panel's own gating decisions,
 * including holding every choice back until the saved one has loaded.
 * `.spec.ts` for jsdom.
 */

import { beforeEach, describe, expect, it, vi } from 'vitest'
import { defineComponent, h, ref } from 'vue'
import { mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'

const settings = vi.hoisted(() => ({ loaded: true }))

vi.mock('@/composables/useAiProviderSettings', () => ({
  useAiProviderSettings: () => ({
    loaded: ref(settings.loaded),
    deploymentMode: ref(null),
    provider: ref('claude'),
    providers: ref([]),
    caps: ref(null),
    savedCaps: ref(null),
    savedMode: ref(null),
    authMode: ref('api_key'),
    tiles: ref([]),
    requiresSecret: ref(false),
    mode: ref(null),
    credential: ref(''),
    hasStoredCredential: ref(false),
    baseUrl: ref(''),
    model: ref(''),
    thinkingChoice: ref(null),
    saving: ref(false),
    canSave: ref(true),
    dirty: ref(false),
    test: ref('idle'),
    testError: ref(''),
    testVersion: ref(''),
    showInstallHint: ref(false),
    selectProvider: vi.fn(),
    save: vi.fn(),
    runTest: vi.fn(),
    load: vi.fn(),
  }),
}))

const { default: SettingsClaudeCode } = await import('../SettingsClaudeCode.vue')
const { useAuthStore } = await import('@/stores/auth')

const slotted = (tag: string) =>
  defineComponent({
    inheritAttrs: false,
    setup(_, { slots }) {
      return () => h(tag, slots.default?.())
    },
  })

const STUBS = {
  'v-btn': slotted('button'),
  AppCallout: slotted('aside'),
  ChoiceTiles: true,
  AiHostFields: true,
  PasswordField: true,
}

function mountAs(permissions: string[]) {
  useAuthStore().user = { id: 'me', permissions } as never
  return mount(SettingsClaudeCode, { global: { stubs: STUBS } })
}

beforeEach(() => {
  setActivePinia(createPinia())
  settings.loaded = true
})

describe('SettingsClaudeCode', () => {
  it('hides Save and Test connection without integrations:configure', () => {
    const wrapper = mountAs(['integrations:view'])

    expect(wrapper.findAll('button')).toHaveLength(0)
    expect(wrapper.text()).toContain('Configure Integrations permission')
  })

  it('offers Save and Test connection with integrations:configure', () => {
    const wrapper = mountAs(['integrations:view', 'integrations:configure'])

    expect(wrapper.findAll('button').map(b => b.text())).toEqual(['Save', 'Test connection'])
  })

  it('offers no choice until the saved settings have loaded', () => {
    settings.loaded = false
    const wrapper = mountAs(['integrations:view', 'integrations:configure'])

    expect(wrapper.findComponent({ name: 'ChoiceTiles' }).exists()).toBe(false)
    expect(wrapper.findAll('button')).toHaveLength(0)
    expect(wrapper.find('[aria-label="Loading the AI settings"]').exists()).toBe(true)
  })
})
