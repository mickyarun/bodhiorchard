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
import type { LeaderboardEntry } from '@/types'
import { ordinal, splitPodium, uniqueByUser, xpBoard, xpNote } from './leaderboard'

function xp(user_id: string, total_xp: number, over: Partial<LeaderboardEntry> = {}): LeaderboardEntry {
  return { user_id, name: user_id, avatar_url: null, total_xp, level: 2, level_name: 'x', streak_count: 0, ...over }
}

describe('leaderboard', () => {
  it('writes ordinals', () => {
    expect([1, 2, 3, 4, 11, 12, 13, 21, 22, 101].map(ordinal)).toEqual([
      '1st', '2nd', '3rd', '4th', '11th', '12th', '13th', '21st', '22nd', '101st',
    ])
  })

  it('splits off a top three only when there is one', () => {
    const e = (key: string) => ({ key, name: key, figure: '1' })
    expect(splitPodium([e('a'), e('b')]).podium).toEqual([])
    expect(splitPodium([e('a'), e('b')]).rest.map(r => r.rank)).toEqual([1, 2])
    const { podium, rest } = splitPodium([e('a'), e('b'), e('c'), e('d')])
    expect(podium.map(p => p.key)).toEqual(['a', 'b', 'c'])
    expect(rest).toEqual([{ key: 'd', name: 'd', figure: '1', rank: 4 }])
  })

  it('keeps the first row per user', () => {
    expect(uniqueByUser([xp('a', 3), xp('a', 1), xp('b', 2)]).map(r => r.total_xp)).toEqual([3, 2])
  })

  it('notes the level and any streak', () => {
    expect(xpNote({ level: 4, streak_count: 0 })).toBe('Level 4')
    expect(xpNote({ level: 4, streak_count: 3 })).toBe('Level 4 · 3-day streak')
  })

  it('builds XP entries with bars relative to the leader', () => {
    const board = xpBoard([xp('a', 1240), xp('b', 620), xp('a', 5)], 'b')
    expect(board.map(b => [b.key, b.figure, b.bar, b.isMe])).toEqual([
      ['a', '1,240', 100, false],
      ['b', '620', 50, true],
    ])
    expect(xpBoard([xp('z', 0)], 'z')[0].bar).toBe(0)
  })

  it('carries each person\'s photo onto the board', () => {
    const board = xpBoard([xp('a', 2, { avatar_url: '/api/v1/employees/avatars/a' }), xp('b', 1)], 'b')
    expect(board.map(b => b.avatarUrl)).toEqual(['/api/v1/employees/avatars/a', null])
  })
})
