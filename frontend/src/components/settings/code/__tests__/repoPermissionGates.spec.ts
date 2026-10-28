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
 * Settings → Code only offers repository changes to members holding
 * settings:edit, the permission every repo-changing route requires.
 *
 * Vuetify and the tab forms are stubbed, so these test the components' own
 * gating decisions rather than Vuetify's rendering. `.spec.ts` for jsdom.
 */

import { beforeEach, describe, expect, it, vi } from 'vitest'
import { defineComponent, h, ref } from 'vue'
import { mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import type { RepoInfo } from '@/types'

vi.mock('@/services/api', () => ({ default: { get: vi.fn(), post: vi.fn(), patch: vi.fn() } }))
vi.mock('@/composables/useDeploymentMode', () => ({
  useDeploymentMode: () => ({ mode: ref('host'), deployPublicKey: ref(''), loadMode: vi.fn() }),
}))

const { default: RepoAddDialog } = await import('../RepoAddDialog.vue')
const { default: RepoListRow } = await import('../RepoListRow.vue')
const { useAuthStore } = await import('@/stores/auth')

const slotted = (tag: string) =>
  defineComponent({
    inheritAttrs: false,
    setup(_, { slots }) {
      return () => h(tag, slots.default?.())
    },
  })

const named = (name: string) =>
  defineComponent({ inheritAttrs: false, setup: () => () => h('div', { 'data-stub': name }) })

const STUBS = {
  'v-dialog': slotted('div'),
  'v-card': slotted('div'),
  'v-btn': slotted('button'),
  'v-chip': slotted('em'),
  'v-icon': true,
  'v-spacer': true,
  'v-checkbox': true,
  'v-checkbox-btn': true,
  'v-avatar': slotted('span'),
  'v-skeleton-loader': true,
  AppCallout: slotted('aside'),
  RepoLocalPickForm: named('local-form'),
  RepoCloneForm: named('clone-form'),
  RepoOnboardBulkTab: named('bulk-tab'),
  RepoRowMenu: named('row-menu'),
  RepoSetupStatusChip: true,
  RepoClassificationChips: true,
  ScanRowTrack: true,
  BranchChip: defineComponent({
    props: ['disabled'],
    emits: ['click'],
    setup(props, { emit }) {
      return () =>
        h('span', {
          'data-stub': 'branch-chip',
          onClick: () => {
            if (!props.disabled) emit('click')
          },
        })
    },
  }),
}

const REPO = {
  id: 'r1',
  name: 'web',
  path: '/repos/web',
  status: 'active',
  mainBranch: 'main',
  developBranch: 'develop',
  uatBranch: null,
  featureCount: 0,
} as unknown as RepoInfo

function signInWith(permissions: string[]): void {
  useAuthStore().user = { id: 'me', permissions } as never
}

function mountDialog() {
  return mount(RepoAddDialog, {
    props: { modelValue: true, branches: {} as never },
    global: { stubs: STUBS },
  })
}

function mountRow() {
  return mount(RepoListRow, {
    props: {
      repo: REPO,
      selectable: true,
      selected: false,
      uatEnabled: false,
      busy: false,
      hasDivider: false,
      isLocked: false,
      run: null,
    },
    global: { stubs: STUBS },
  })
}

beforeEach(() => {
  setActivePinia(createPinia())
})

describe('RepoAddDialog', () => {
  it('explains the missing permission instead of offering any add path', () => {
    signInWith(['settings:view', 'integrations:configure'])
    const wrapper = mountDialog()

    expect(wrapper.find('aside').exists()).toBe(true)
    expect(wrapper.find('aside').text()).toContain('Ask an org admin')
    for (const stub of ['local-form', 'clone-form', 'bulk-tab']) {
      expect(wrapper.find(`[data-stub="${stub}"]`).exists()).toBe(false)
    }
    expect(wrapper.find('footer').exists()).toBe(false)
  })

  it('offers the add forms to a member with settings:edit', () => {
    signInWith(['settings:edit'])
    const wrapper = mountDialog()

    expect(wrapper.find('aside').exists()).toBe(false)
    expect(wrapper.find('[data-stub="local-form"]').exists()).toBe(true)
    expect(wrapper.find('footer').exists()).toBe(true)
  })
})

describe('RepoListRow', () => {
  it('is read-only without settings:edit: no action menu, branch chips inert', async () => {
    signInWith(['settings:view'])
    const wrapper = mountRow()

    expect(wrapper.find('[data-stub="row-menu"]').exists()).toBe(false)
    await wrapper.find('[data-stub="branch-chip"]').trigger('click')
    expect(wrapper.emitted('edit-branches')).toBeUndefined()
  })

  it('offers the action menu and branch editing with settings:edit', async () => {
    signInWith(['settings:edit'])
    const wrapper = mountRow()

    expect(wrapper.find('[data-stub="row-menu"]').exists()).toBe(true)
    await wrapper.find('[data-stub="branch-chip"]').trigger('click')
    expect(wrapper.emitted('edit-branches')).toHaveLength(1)
  })
})
