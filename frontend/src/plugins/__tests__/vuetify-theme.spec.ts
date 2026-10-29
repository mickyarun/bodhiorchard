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

/** Cards stay flat on the page but lift off it inside a menu. */

import { mount } from '@vue/test-utils'
import { describe, expect, it, vi } from 'vitest'
import { defineComponent, nextTick } from 'vue'
import { createVuetify } from 'vuetify'
import { VCard, VMenu } from 'vuetify/components'
import { vuetifyDefaults } from '../vuetify-theme'

// jsdom has neither; the menu's positioning only needs them to exist.
vi.stubGlobal('ResizeObserver', class { observe(): void {} unobserve(): void {} disconnect(): void {} })
vi.stubGlobal('visualViewport', Object.assign(new EventTarget(), { width: 1024, height: 768, scale: 1 }))

const Harness = defineComponent({
  components: { VCard, VMenu },
  template: `
    <div>
      <v-card class="page-card">On the page</v-card>
      <v-menu :model-value="true" attach="body">
        <template #activator="{ props }"><button v-bind="props">Open</button></template>
        <v-card class="menu-card">In the menu</v-card>
      </v-menu>
    </div>`,
})

describe('vuetifyDefaults', () => {
  it('gives a card inside a menu a shadow and a border, and leaves page cards flat', async () => {
    const wrapper = mount(Harness, {
      attachTo: document.body,
      global: { plugins: [createVuetify({ defaults: vuetifyDefaults })] },
    })
    try {
      await nextTick()
      await nextTick()

      const menuCard = document.querySelector('.menu-card')
      expect(menuCard?.classList.contains('elevation-8')).toBe(true)
      expect(menuCard?.classList.contains('v-card--border')).toBe(true)
      expect(wrapper.find('.page-card').classes()).toContain('elevation-0')
    } finally {
      wrapper.unmount()
    }
  })
})
