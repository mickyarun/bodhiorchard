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

import { describe, expect, it } from 'vitest'
import {
  FLOOR_FLASH_MS,
  PADS,
  START_FLASH_MS,
  type PadId,
  extendSequence,
  flashDurationForLevel,
  isRoundComplete,
  matchStep,
  randomPad,
} from '../colorRecall'

const PAD_IDS = PADS.map((p) => p.id)

/** Deterministic RNG that walks a fixed list of [0,1) values, then repeats. */
function seededRng(values: number[]): () => number {
  let i = 0
  return () => values[i++ % values.length]
}

describe('PADS', () => {
  it('has four pads with unique ids and glyphs', () => {
    expect(PADS).toHaveLength(4)
    expect(new Set(PAD_IDS).size).toBe(4)
    expect(new Set(PADS.map((p) => p.glyph)).size).toBe(4)
  })
})

describe('randomPad', () => {
  it('only ever returns a valid pad id', () => {
    const rng = seededRng([0, 0.26, 0.5, 0.76, 0.999])
    for (let n = 0; n < 5; n++) {
      expect(PAD_IDS).toContain(randomPad(rng))
    }
  })

  it('maps rng buckets to pads in board order', () => {
    expect(randomPad(() => 0)).toBe(PAD_IDS[0])
    expect(randomPad(() => 0.999)).toBe(PAD_IDS[3])
  })
})

describe('extendSequence', () => {
  it('appends exactly one valid pad without mutating the input', () => {
    const seq: PadId[] = ['emerald', 'amber']
    const next = extendSequence(seq, () => 0.999)
    expect(next).toHaveLength(3)
    expect(next.slice(0, 2)).toEqual(seq)
    expect(PAD_IDS).toContain(next[2])
    expect(seq).toHaveLength(2) // original untouched
  })

  it('never repeats the previous pad back-to-back', () => {
    const rngs = [() => 0, () => 0.34, () => 0.67, () => 0.999]
    for (const prev of PAD_IDS) {
      for (const rng of rngs) {
        expect(extendSequence([prev], rng)[1]).not.toBe(prev)
      }
    }
  })

  it('builds a whole sequence with no adjacent repeats', () => {
    const walk = seededRng([0.1, 0.45, 0.8, 0.3, 0.6, 0.95, 0.2, 0.5])
    let seq: PadId[] = []
    for (let n = 0; n < 9; n++) seq = extendSequence(seq, walk)
    for (let k = 1; k < seq.length; k++) {
      expect(seq[k]).not.toBe(seq[k - 1])
    }
  })
})

describe('matchStep', () => {
  const seq: PadId[] = ['emerald', 'sky', 'rose']
  it('returns ok when the tap matches the expected step', () => {
    expect(matchStep(seq, 0, 'emerald')).toBe('ok')
    expect(matchStep(seq, 1, 'sky')).toBe('ok')
  })
  it('returns wrong for any other pad', () => {
    expect(matchStep(seq, 0, 'amber')).toBe('wrong')
    expect(matchStep(seq, 2, 'sky')).toBe('wrong')
  })
})

describe('isRoundComplete', () => {
  const seq: PadId[] = ['emerald', 'sky']
  it('is false until every step is tapped', () => {
    expect(isRoundComplete(seq, 0)).toBe(false)
    expect(isRoundComplete(seq, 1)).toBe(false)
  })
  it('is true once the tap count reaches the sequence length', () => {
    expect(isRoundComplete(seq, 2)).toBe(true)
  })
})

describe('flashDurationForLevel — contract (always holds)', () => {
  const levels = Array.from({ length: 30 }, (_, i) => i + 1)

  it('starts readable at level 1', () => {
    expect(flashDurationForLevel(1)).toBe(START_FLASH_MS)
  })

  it('never drops below the floor', () => {
    for (const level of levels) {
      expect(flashDurationForLevel(level)).toBeGreaterThanOrEqual(FLOOR_FLASH_MS)
    }
  })

  it('is monotonically non-increasing as levels climb', () => {
    for (let i = 1; i < levels.length; i++) {
      expect(flashDurationForLevel(levels[i])).toBeLessThanOrEqual(
        flashDurationForLevel(levels[i - 1]),
      )
    }
  })
})

// The difficulty curve's engagement + competitiveness guarantees: a gentle
// early ramp (first-session retention) and a speed dimension that keeps
// separating players through the competitive scoring band before it floors.
describe('flashDurationForLevel — engagement & competitive design', () => {
  it('speeds up but stays gentle in the opening rounds', () => {
    expect(flashDurationForLevel(3)).toBeLessThan(flashDurationForLevel(1))
    expect(flashDurationForLevel(2)).toBeGreaterThan(540) // not punishing early
  })

  it('keeps speed relevant through the competitive band, then caps', () => {
    expect(flashDurationForLevel(8)).toBeGreaterThan(FLOOR_FLASH_MS) // still ramping
    expect(flashDurationForLevel(30)).toBe(FLOOR_FLASH_MS) // capped at the human limit
  })
})
