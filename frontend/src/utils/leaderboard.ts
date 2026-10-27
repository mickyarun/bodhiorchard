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
 * One shape for every leaderboard (XP, quiz, racing, mini games) so they
 * share the top-three cards and the ranked list.
 */
import type { LeaderboardEntry } from '@/types'

export interface BoardEntry {
  key: string
  name: string
  /** The headline number, already formatted: "1,240", "0:42.1". */
  figure: string
  /** Small unit after the figure: "XP", "pts". */
  unit?: string
  /** One line under the name: "Level 4 · 3-day streak". */
  note?: string
  isMe?: boolean
  /** 0–100 for the progress bar on list rows; leave out for no bar. */
  bar?: number
}

export interface RankedEntry extends BoardEntry {
  rank: number
}

/** The cards need a full top three; with fewer, everyone goes in the list. */
export const PODIUM_SIZE = 3

/** "1st", "2nd", "3rd", "4th", "11th", "22nd". */
export function ordinal(n: number): string {
  const teen = n % 100 >= 11 && n % 100 <= 13
  const suffix = teen ? 'th' : ({ 1: 'st', 2: 'nd', 3: 'rd' } as Record<number, string>)[n % 10] ?? 'th'
  return `${n}${suffix}`
}

/** Ranks entries in order and splits off the top three when there are at least three. */
export function splitPodium(entries: BoardEntry[]): { podium: RankedEntry[]; rest: RankedEntry[] } {
  const ranked = entries.map((e, i) => ({ ...e, rank: i + 1 }))
  if (ranked.length < PODIUM_SIZE) return { podium: [], rest: ranked }
  return { podium: ranked.slice(0, PODIUM_SIZE), rest: ranked.slice(PODIUM_SIZE) }
}

/** First row per user; the API can return a user twice through a join. */
export function uniqueByUser<T extends { user_id: string }>(rows: T[]): T[] {
  const seen = new Set<string>()
  return rows.filter(r => (seen.has(r.user_id) ? false : (seen.add(r.user_id), true)))
}

/** "Level 4 · 3-day streak". The level names are left out on purpose. */
export function xpNote(e: Pick<LeaderboardEntry, 'level' | 'streak_count'>): string {
  return e.streak_count > 0 ? `Level ${e.level} · ${e.streak_count}-day streak` : `Level ${e.level}`
}

/** XP board entries, with each bar relative to the leader. */
export function xpBoard(rows: LeaderboardEntry[], myId: string): BoardEntry[] {
  const unique = uniqueByUser(rows)
  const max = Math.max(1, ...unique.map(e => e.total_xp))
  return unique.map(e => ({
    key: e.user_id,
    name: e.name,
    figure: e.total_xp.toLocaleString('en-US'),
    unit: 'XP',
    note: xpNote(e),
    isMe: e.user_id === myId,
    bar: Math.round((e.total_xp / max) * 100),
  }))
}
