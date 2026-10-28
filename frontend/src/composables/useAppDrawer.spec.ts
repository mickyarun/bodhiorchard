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
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { defineComponent, h, nextTick, ref } from 'vue'
import { createMemoryHistory, createRouter } from 'vue-router'
import { useAppDrawer } from './useAppDrawer'

const smAndDown = ref(false)
vi.mock('vuetify', () => ({ useDisplay: () => ({ smAndDown }) }))

async function setup() {
  const router = createRouter({
    history: createMemoryHistory(),
    routes: [{ path: '/:p(.*)*', component: { render: () => null } }],
  })
  await router.push('/dashboard')
  let drawer!: ReturnType<typeof useAppDrawer>
  mount(defineComponent({
    setup() {
      drawer = useAppDrawer()
      return () => h('div')
    },
  }), { global: { plugins: [router] } })
  return drawer
}

describe('useAppDrawer', () => {
  beforeEach(() => {
    localStorage.clear()
    smAndDown.value = false
  })

  it('draws a hovered rail as the open sidebar and an unhovered one collapsed', async () => {
    localStorage.setItem('bodhiorchard_sidebar_rail', 'true')
    const drawer = await setup()
    expect(drawer.rail.value).toBe(true)
    expect(drawer.collapsed.value).toBe(true)

    drawer.onRailHover(false) // Vuetify: pointer entered, rail expanded
    expect(drawer.collapsed.value).toBe(false)
    drawer.onRailHover(true) // pointer left
    expect(drawer.collapsed.value).toBe(true)
  })

  it('stays open when collapsed under the pointer, until the pointer leaves', async () => {
    const drawer = await setup()
    drawer.onRailHover(false)
    drawer.toggleRail()
    expect(drawer.rail.value).toBe(true)
    expect(drawer.collapsed.value).toBe(false)
    drawer.onRailHover(true)
    expect(drawer.collapsed.value).toBe(true)
  })

  it('remembers the rail and never uses it on phones', async () => {
    const drawer = await setup()
    drawer.toggleRail()
    await nextTick()
    expect(localStorage.getItem('bodhiorchard_sidebar_rail')).toBe('true')
    smAndDown.value = true
    expect(drawer.rail.value).toBe(false)
    expect(drawer.collapsed.value).toBe(false)
  })
})
