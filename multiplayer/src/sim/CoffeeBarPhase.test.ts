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
 * Unit tests for CoffeeBarPhase — pure tick logic for the coffee machine.
 * Time is passed explicitly; no fake timers or Colyseus runtime involved.
 */
import { describe, it, expect } from 'vitest'
import {
  advancePhase,
  acknowledgeDispense,
  type PhaseSnapshot,
} from './CoffeeBarPhase'
import { COFFEE_PHASE_MS } from './CoffeeMenu'

const idleSnapshot = (now = 0): PhaseSnapshot => ({
  phase: 'idle',
  phaseStartMs: now,
  userId: '',
  drink: '',
})

describe('CoffeeBarPhase.advancePhase', () => {
  it('idle → approaching when queue has an entry', () => {
    const r = advancePhase(idleSnapshot(1000), { userId: 'u1', drink: 'latte' }, 1500)
    expect(r.next?.phase).toBe('approaching')
    expect(r.next?.userId).toBe('u1')
    expect(r.next?.drink).toBe('latte')
    expect(r.next?.phaseStartMs).toBe(1500)
    expect(r.dequeued).toBe(1)
  })

  it('idle stays idle when queue is empty', () => {
    const r = advancePhase(idleSnapshot(1000), null, 2000)
    expect(r.next).toBeNull()
    expect(r.dequeued).toBe(0)
  })

  it('approaching → brewing after the approach duration', () => {
    const start = 10_000
    const snap: PhaseSnapshot = {
      phase: 'approaching',
      phaseStartMs: start,
      userId: 'u1',
      drink: 'tea',
    }
    // Just before: no transition
    const before = advancePhase(snap, null, start + COFFEE_PHASE_MS.approaching - 1)
    expect(before.next).toBeNull()
    // Exactly at threshold: transition
    const at = advancePhase(snap, null, start + COFFEE_PHASE_MS.approaching)
    expect(at.next?.phase).toBe('brewing')
    expect(at.next?.userId).toBe('u1')
  })

  it('brewing → dispensed sets justDispensed', () => {
    const start = 10_000
    const snap: PhaseSnapshot = {
      phase: 'brewing',
      phaseStartMs: start,
      userId: 'u1',
      drink: 'espresso',
    }
    const r = advancePhase(snap, null, start + COFFEE_PHASE_MS.brewing)
    expect(r.next?.phase).toBe('dispensed')
    expect(r.justDispensed).toBe(true)
    expect(r.justCompleted).toBe(false)
  })

  it('dispensed times out back to idle with justCompleted', () => {
    const start = 10_000
    const snap: PhaseSnapshot = {
      phase: 'dispensed',
      phaseStartMs: start,
      userId: 'u1',
      drink: 'latte',
    }
    const r = advancePhase(snap, null, start + COFFEE_PHASE_MS.dispensed)
    expect(r.next?.phase).toBe('idle')
    expect(r.next?.userId).toBe('')
    expect(r.justCompleted).toBe(true)
  })
})

describe('CoffeeBarPhase.acknowledgeDispense', () => {
  it('advances dispensed → idle for the matching user', () => {
    const snap: PhaseSnapshot = {
      phase: 'dispensed',
      phaseStartMs: 1000,
      userId: 'u1',
      drink: 'latte',
    }
    const r = acknowledgeDispense(snap, 'u1', 2000)
    expect(r.next?.phase).toBe('idle')
    expect(r.justCompleted).toBe(true)
  })

  it('ignores acks from a different user', () => {
    const snap: PhaseSnapshot = {
      phase: 'dispensed',
      phaseStartMs: 1000,
      userId: 'u1',
      drink: 'latte',
    }
    const r = acknowledgeDispense(snap, 'u2', 2000)
    expect(r.next).toBeNull()
  })

  it('ignores acks when not in dispensed phase', () => {
    const snap: PhaseSnapshot = {
      phase: 'brewing',
      phaseStartMs: 1000,
      userId: 'u1',
      drink: 'latte',
    }
    const r = acknowledgeDispense(snap, 'u1', 2000)
    expect(r.next).toBeNull()
  })
})
