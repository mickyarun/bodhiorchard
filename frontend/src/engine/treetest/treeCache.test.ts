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
import { isStructurallyValid, SCHEMA_VERSION, type BakedTree } from './treeCache'

function makeTree(overrides: Partial<BakedTree>): BakedTree {
  return {
    schemaVersion: SCHEMA_VERSION,
    cacheKey: 'repo|0|1|abc',
    savedAt: 0,
    branchGroups: [{ colorKey: 'k', color: [96, 66, 42], matrices: new Float32Array(16), count: 1 }],
    leafGroup: null,
    primaries: [],
    labelY: 1,
    ...overrides,
  }
}

describe('isStructurallyValid', () => {
  it('accepts a well-formed baked tree', () => {
    expect(isStructurallyValid(makeTree({}))).toBe(true)
  })

  it('accepts multiple branch groups with matching matrix lengths', () => {
    const tree = makeTree({
      branchGroups: [
        { colorKey: 'a', color: [96, 66, 42], matrices: new Float32Array(32), count: 2 },
        { colorKey: 'b', color: [76, 158, 60], matrices: new Float32Array(48), count: 3 },
      ],
    })
    expect(isStructurallyValid(tree)).toBe(true)
  })

  it('rejects an entry with zero branch groups (a tree always has a trunk)', () => {
    expect(isStructurallyValid(makeTree({ branchGroups: [] }))).toBe(false)
  })

  it('rejects a group with count 0', () => {
    const tree = makeTree({
      branchGroups: [{ colorKey: 'k', color: [96, 66, 42], matrices: new Float32Array(0), count: 0 }],
    })
    expect(isStructurallyValid(tree)).toBe(false)
  })

  it('rejects a matrix buffer whose length does not match count * 16 (partial write)', () => {
    const tree = makeTree({
      branchGroups: [{ colorKey: 'k', color: [96, 66, 42], matrices: new Float32Array(20), count: 2 }],
    })
    expect(isStructurallyValid(tree)).toBe(false)
  })
})
