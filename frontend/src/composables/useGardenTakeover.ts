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

import { onMounted, onUnmounted, ref, type Ref } from 'vue'

/** The slice of the garden view the takeover controls need. */
export interface TakeoverTarget {
  takeoverCharacter: () => void
  exitTakeover: () => void
  exitHouse: () => void
  isTakeover: () => boolean
  isInControl: () => boolean
}

const SYNC_MS = 500

/**
 * "T" takes control of your character in the 3D garden (and leaves it, or
 * a house interior). The engine can also hand control back on its own (a
 * door, ESC, auto-exit), so ``inControl`` is re-read on a short interval.
 */
export function useGardenTakeover(target: Ref<TakeoverTarget | null>, active: () => boolean) {
  const inControl = ref(false)
  let sync: ReturnType<typeof setInterval> | null = null

  function readState(): void {
    inControl.value = target.value?.isInControl() ?? false
  }

  function toggle(): void {
    const garden = target.value
    if (!garden) return
    if (!garden.isInControl()) garden.takeoverCharacter()
    else if (garden.isTakeover()) garden.exitTakeover()
    else garden.exitHouse()
    // Takeover settles asynchronously; read it back once it has.
    setTimeout(readState, 100)
  }

  function onKeyDown(e: KeyboardEvent): void {
    if (e.key !== 't' && e.key !== 'T') return
    const tag = (e.target as HTMLElement | null)?.tagName
    if (tag === 'INPUT' || tag === 'TEXTAREA' || tag === 'SELECT') return
    if (active()) toggle()
  }

  onMounted(() => {
    window.addEventListener('keydown', onKeyDown)
    sync = setInterval(readState, SYNC_MS)
  })

  onUnmounted(() => {
    window.removeEventListener('keydown', onKeyDown)
    if (sync) clearInterval(sync)
  })

  return { inControl }
}
