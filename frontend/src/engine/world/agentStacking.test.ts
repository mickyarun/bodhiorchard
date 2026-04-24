// SPDX-License-Identifier: AGPL-3.0-or-later
// Copyright (C) 2026 Arun Rajkumar

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
