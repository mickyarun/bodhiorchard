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

import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'
import { defineComponent, h, type WritableComputedRef } from 'vue'
import { createMemoryHistory, createRouter } from 'vue-router'
import { useDashboardViewMode, type DashboardViewMode } from './useDashboardViewMode'

async function setup(url: string) {
  const router = createRouter({
    history: createMemoryHistory(),
    routes: [{ path: '/dashboard', component: { render: () => null } }],
  })
  await router.push(url)
  let mode!: WritableComputedRef<DashboardViewMode>
  mount(defineComponent({
    setup() {
      mode = useDashboardViewMode()
      return () => h('div')
    },
  }), { global: { plugins: [router] } })
  return { router, mode }
}

describe('useDashboardViewMode', () => {
  it('opens on the overview', async () => {
    expect((await setup('/dashboard')).mode.value).toBe('overview')
  })

  it('keeps old graph links working and ignores unknown views', async () => {
    expect((await setup('/dashboard?view=graph')).mode.value).toBe('graph')
    expect((await setup('/dashboard?view=tree')).mode.value).toBe('overview')
  })

  it('writes the view to the query, keeps other params, and clears it for overview', async () => {
    const { router, mode } = await setup('/dashboard?repo=api')
    mode.value = 'garden'
    await router.isReady()
    await new Promise(r => setTimeout(r))
    expect(router.currentRoute.value.query).toEqual({ repo: 'api', view: 'garden' })
    mode.value = 'overview'
    await new Promise(r => setTimeout(r))
    expect(router.currentRoute.value.query).toEqual({ repo: 'api' })
  })
})
