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
 * Tests run in the default Vitest ``node`` environment — no jsdom is
 * installed. We stub a minimal ``document`` shim with the
 * ``visibilityState`` getter and event-listener surface the composable
 * actually touches, then drive it with ``vi.useFakeTimers``.
 *
 * The composable calls ``onUnmounted`` (a Vue lifecycle hook) which only
 * works inside an active component context. We use ``effectScope`` to
 * create a synthetic context and ``scope.stop()`` to simulate unmount —
 * Vue's lifecycle hooks fire on scope stop the same way they do on
 * component unmount.
 */

import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { effectScope, ref, type Ref } from 'vue'
import { useFocusAwarePoll } from './useFocusAwarePoll'

interface DocumentShim {
  visibilityState: 'visible' | 'hidden'
  addEventListener: (event: string, listener: EventListener) => void
  removeEventListener: (event: string, listener: EventListener) => void
  fire: () => void
}

function makeDocumentShim(): DocumentShim {
  const listeners = new Set<EventListener>()
  const removeSpy = vi.fn()
  const shim: DocumentShim = {
    visibilityState: 'visible',
    addEventListener: (event, listener) => {
      if (event === 'visibilitychange') {
        listeners.add(listener)
      }
    },
    removeEventListener: (event, listener) => {
      removeSpy(event, listener)
      if (event === 'visibilitychange') {
        listeners.delete(listener)
      }
    },
    fire: () => {
      const evt = {} as Event
      for (const l of listeners) {
        l(evt)
      }
    },
  }
  // expose the spy via the same property name for assertions below
  ;(shim as unknown as { removeEventListenerSpy: typeof removeSpy }).removeEventListenerSpy =
    removeSpy
  return shim
}

interface Harness {
  active: Ref<boolean>
  callback: ReturnType<typeof vi.fn>
  stop: () => void
}

function mount(intervalMs: number, initialActive: boolean): Harness {
  const active = ref(initialActive)
  const callback = vi.fn()
  callback.mockResolvedValue(undefined)
  const scope = effectScope()
  scope.run(() => {
    useFocusAwarePoll(() => callback() as Promise<void>, intervalMs, { active })
  })
  return { active, callback, stop: () => scope.stop() }
}

describe('useFocusAwarePoll', () => {
  let doc: DocumentShim

  beforeEach(() => {
    vi.useFakeTimers()
    doc = makeDocumentShim()
    vi.stubGlobal('document', doc)
  })

  afterEach(() => {
    vi.useRealTimers()
    vi.unstubAllGlobals()
  })

  it('polls on the interval when active and visible', () => {
    const h = mount(500, true)
    vi.advanceTimersByTime(1500)
    expect(h.callback).toHaveBeenCalledTimes(3)
    h.stop()
  })

  it('does not poll when inactive', () => {
    const h = mount(500, false)
    vi.advanceTimersByTime(2000)
    expect(h.callback).not.toHaveBeenCalled()
    h.stop()
  })

  it('pauses on visibility change to hidden, resumes when visible', () => {
    const h = mount(500, true)
    vi.advanceTimersByTime(500)
    expect(h.callback).toHaveBeenCalledTimes(1)

    doc.visibilityState = 'hidden'
    doc.fire()
    vi.advanceTimersByTime(2000)
    expect(h.callback).toHaveBeenCalledTimes(1)

    doc.visibilityState = 'visible'
    doc.fire()
    vi.advanceTimersByTime(500)
    expect(h.callback).toHaveBeenCalledTimes(2)

    h.stop()
  })

  it('stops polling and removes listener on scope stop (unmount)', () => {
    const h = mount(500, true)
    vi.advanceTimersByTime(500)
    expect(h.callback).toHaveBeenCalledTimes(1)

    h.stop()
    vi.advanceTimersByTime(5000)
    expect(h.callback).toHaveBeenCalledTimes(1)
    const spy = (doc as unknown as { removeEventListenerSpy: ReturnType<typeof vi.fn> })
      .removeEventListenerSpy
    expect(spy).toHaveBeenCalledWith('visibilitychange', expect.any(Function))
  })

  it('stops polling when active flips to false', async () => {
    const h = mount(500, true)
    vi.advanceTimersByTime(500)
    expect(h.callback).toHaveBeenCalledTimes(1)

    h.active.value = false
    await Promise.resolve()
    vi.advanceTimersByTime(2000)
    expect(h.callback).toHaveBeenCalledTimes(1)

    h.stop()
  })
})
