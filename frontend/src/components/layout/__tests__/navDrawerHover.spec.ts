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
 * The sidebar learns that a rail is hovered from the drawer's
 * ``update:rail`` event (see useAppDrawer). That is Vuetify behaviour, not
 * ours, so this pins it against a real drawer: an upgrade that changes it
 * fails here instead of quietly breaking the sidebar layout.
 */
import { mount } from '@vue/test-utils'
import { describe, expect, it, vi } from 'vitest'
import { h, nextTick } from 'vue'
import { createVuetify } from 'vuetify'
import { VLayout } from 'vuetify/components/VLayout'
import { VNavigationDrawer } from 'vuetify/components/VNavigationDrawer'

vi.stubGlobal('ResizeObserver', class { observe(): void {} unobserve(): void {} disconnect(): void {} })

describe('VNavigationDrawer with rail and expand-on-hover', () => {
  it('emits update:rail false on pointer enter and true on leave', async () => {
    const onRail = vi.fn()
    const wrapper = mount(VLayout, {
      global: { plugins: [createVuetify()] },
      slots: {
        default: () => h(VNavigationDrawer, {
          rail: true,
          expandOnHover: true,
          permanent: true,
          'onUpdate:rail': onRail,
        }),
      },
    })
    const drawer = wrapper.find('.v-navigation-drawer')
    await drawer.trigger('mouseenter')
    await vi.waitFor(() => expect(onRail).toHaveBeenLastCalledWith(false))
    await drawer.trigger('mouseleave')
    await nextTick()
    await vi.waitFor(() => expect(onRail).toHaveBeenLastCalledWith(true))
  })
})
