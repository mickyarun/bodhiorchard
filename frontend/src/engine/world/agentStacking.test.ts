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

import { describe, it, expect } from 'vitest'
import { countAgentsAtRepo } from '@shared/world/agentStacking'

interface TestEntry {
  repoNames: string[]
  currentRepoIndex: number
  key: string
  alive: boolean
}

const entry = (repo: string, key: string, alive = true): TestEntry => ({
  repoNames: [repo],
  currentRepoIndex: 0,
  key,
  alive,
})

describe('countAgentsAtRepo', () => {
  it('returns 0 for empty iterable', () => {
    expect(countAgentsAtRepo([], 'repo-a')).toBe(0)
  })

  it('counts only entries whose current repo matches', () => {
    const entries = [entry('repo-a', 'k1'), entry('repo-b', 'k2'), entry('repo-a', 'k3')]
    expect(countAgentsAtRepo(entries, 'repo-a')).toBe(2)
    expect(countAgentsAtRepo(entries, 'repo-b')).toBe(1)
    expect(countAgentsAtRepo(entries, 'nope')).toBe(0)
  })

  it('respects currentRepoIndex when entries are multi-repo', () => {
    const multi: TestEntry[] = [
      { repoNames: ['repo-a', 'repo-b'], currentRepoIndex: 1, key: 'k1', alive: true },
    ]
    expect(countAgentsAtRepo(multi, 'repo-a')).toBe(0)
    expect(countAgentsAtRepo(multi, 'repo-b')).toBe(1)
  })

  it('applies the isActive predicate when provided', () => {
    const entries = [
      entry('repo-a', 'k1', true),
      entry('repo-a', 'k2', false),
      entry('repo-a', 'k3', true),
    ]
    expect(countAgentsAtRepo(entries, 'repo-a', e => e.alive)).toBe(2)
    expect(countAgentsAtRepo(entries, 'repo-a')).toBe(3)
  })

  it('predicate can close over caller-only fields not declared on StackEntry', () => {
    const aliveKeys = new Set(['k1', 'k3'])
    const entries = [entry('repo-a', 'k1'), entry('repo-a', 'k2'), entry('repo-a', 'k3')]
    expect(countAgentsAtRepo(entries, 'repo-a', e => aliveKeys.has(e.key))).toBe(2)
  })
})
