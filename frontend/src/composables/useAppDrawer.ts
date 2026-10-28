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

import { computed, ref, watch } from 'vue'
import { useRoute } from 'vue-router'
import { useDisplay } from 'vuetify'

// Storage key predates the rename; installs already carry it.
const RAIL_KEY = 'bodhiorchard_sidebar_rail'

/**
 * Sidebar state. On wide screens the sidebar is permanent and can collapse
 * to an icon rail (remembered across reloads); hovering a rail expands it
 * over the page. On phones and small tablets it is an overlay opened from
 * the top bar, always full width, and closes when the user picks a page.
 *
 * ``rail`` is the drawer's mode; ``collapsed`` is what is drawn: a rail the
 * pointer is not over. Everything inside the drawer lays itself out from
 * ``collapsed``, so a hovered rail looks exactly like the open sidebar.
 */
export function useAppDrawer() {
  const display = useDisplay()
  const route = useRoute()

  const compact = computed(() => display.smAndDown.value)
  const railPreference = ref(localStorage.getItem(RAIL_KEY) === 'true')
  /** Whether the sidebar is drawn as a rail right now; never on phones. */
  const rail = computed(() => railPreference.value && !compact.value)
  const overlayOpen = ref(false)
  /** The pointer is over the drawer (Vuetify's own hover state). */
  const hovered = ref(false)
  const collapsed = computed(() => rail.value && !hovered.value)

  watch(railPreference, v => localStorage.setItem(RAIL_KEY, String(v)))
  watch(() => route.fullPath, () => { overlayOpen.value = false })

  function toggleRail(): void {
    railPreference.value = !railPreference.value
  }

  /**
   * The drawer's ``update:rail`` event. With expand-on-hover Vuetify emits
   * ``false`` when the pointer enters the drawer and ``true`` when it
   * leaves (after its open/close delay), whether or not it is a rail at
   * that moment, so collapsing it under the pointer stays in step too.
   */
  function onRailHover(stillRail: boolean): void {
    hovered.value = !stillRail
  }

  return { compact, rail, collapsed, railPreference, overlayOpen, toggleRail, onRailHover }
}
