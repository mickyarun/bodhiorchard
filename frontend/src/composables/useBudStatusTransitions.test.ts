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

import { beforeEach, describe, expect, it, vi } from 'vitest'
import { useBudStatusTransitions } from './useBudStatusTransitions'

const updateBUD = vi.fn()

vi.mock('@/stores/bud', () => ({
  useBUDStore: () => ({ updateBUD, error: '' }),
}))

function makeController(status = 'prod') {
  return useBudStatusTransitions({
    getBud: () => ({ id: 'bud-1', status } as never),
    setActiveTab: vi.fn(),
    getStatusTabMap: () => ({ closed: 'closed', design: 'design' }),
    triggerDesignGeneration: vi.fn(),
    reloadTimeline: vi.fn().mockResolvedValue(undefined),
  })
}

describe('useBudStatusTransitions', () => {
  beforeEach(() => {
    updateBUD.mockReset()
    updateBUD.mockResolvedValue({})
  })

  it('asks before closing and only closes once confirmed', async () => {
    const c = makeController()
    await c.updateStatus('closed')
    expect(c.showCloseConfirmDialog.value).toBe(true)
    expect(updateBUD).not.toHaveBeenCalled()

    await c.confirmClose()
    expect(c.showCloseConfirmDialog.value).toBe(false)
    expect(updateBUD).toHaveBeenCalledWith('bud-1', { status: 'closed' })
  })

  it('ignores a second stage change while one is in flight', async () => {
    let finish: (v: unknown) => void = () => {}
    updateBUD.mockReturnValue(new Promise(resolve => { finish = resolve }))
    const c = makeController('bud')

    const first = c.updateStatus('design')
    expect(c.changingStatus.value).toBe(true)
    await c.updateStatus('design')
    expect(updateBUD).toHaveBeenCalledTimes(1)

    finish({})
    await first
    expect(c.changingStatus.value).toBe(false)
  })
})
