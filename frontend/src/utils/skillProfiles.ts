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
 * Pure helpers for the Skills page: level words, the person and area
 * groupings, the search filter and the one-line summary under a card.
 * Scores arrive from the API as 0–1 expertise weights per code module.
 */
import type { ModuleSkill, SkillProfile } from '@/types'

export type SkillLevel = 'Expert' | 'Strong' | 'Familiar'

/** Scores at or above these read as the level beside them. */
const EXPERT_FROM = 0.75
const STRONG_FROM = 0.45

/** Share of commits one top-level area needs before a person is "mostly in" it. */
const MOSTLY_SHARE = 0.5

export interface AreaContributor {
  userName: string
  email: string
  score: number
  touchCount: number
}

export interface SkillArea {
  name: string
  languages: string[]
  people: AreaContributor[]
}

export function skillLevel(score: number): SkillLevel {
  if (score >= EXPERT_FROM) return 'Expert'
  if (score >= STRONG_FROM) return 'Strong'
  return 'Familiar'
}

/** A 0–1 score as a whole percentage, clamped so a bar never overflows. */
export function scorePercent(score: number): number {
  return Math.round(Math.min(1, Math.max(0, score)) * 100)
}

export function sortByScore<T extends { score: number }>(items: T[]): T[] {
  return [...items].sort((a, b) => b.score - a.score)
}

export function plural(n: number, word: string, many = `${word}s`): string {
  return `${n} ${n === 1 ? word : many}`
}

/** First path segment of a module name: ``payments/refunds`` → ``payments``. */
export function topLevelArea(moduleName: string): string {
  return moduleName.split('/')[0] || moduleName
}

/**
 * "Mostly in payments · 132 commits" when one top-level area holds most
 * of a person's commits, otherwise "Across 3 areas · 132 commits".
 */
export function profileSummary(modules: ModuleSkill[]): string {
  const commits = modules.reduce((sum, m) => sum + m.touchCount, 0)
  const byArea = new Map<string, number>()
  for (const m of modules) {
    const area = topLevelArea(m.name)
    byArea.set(area, (byArea.get(area) ?? 0) + m.touchCount)
  }
  const [topArea, topCommits] = [...byArea.entries()].sort((a, b) => b[1] - a[1])[0] ?? ['', 0]
  const where = commits > 0 && topCommits / commits > MOSTLY_SHARE
    ? `Mostly in ${topArea}`
    : `Across ${plural(byArea.size, 'area')}`
  return `${where} · ${plural(commits, 'commit')}`
}

/** Regroups person → modules into module → people, most-shared areas first. */
export function groupByArea(profiles: SkillProfile[]): SkillArea[] {
  const map = new Map<string, SkillArea>()
  for (const profile of profiles) {
    for (const mod of profile.modules) {
      const area = map.get(mod.name) ?? { name: mod.name, languages: [], people: [] }
      map.set(mod.name, area)
      area.people.push({
        userName: profile.userName,
        email: profile.email,
        score: mod.score,
        touchCount: mod.touchCount,
      })
      for (const lang of mod.languages) {
        if (!area.languages.includes(lang)) area.languages.push(lang)
      }
    }
  }
  const areas = [...map.values()].map(a => ({ ...a, people: sortByScore(a.people) }))
  return areas.sort((a, b) => b.people.length - a.people.length || a.name.localeCompare(b.name))
}

function matches(text: string, query: string): boolean {
  return text.toLowerCase().includes(query)
}

export function filterProfiles(profiles: SkillProfile[], query: string): SkillProfile[] {
  const q = query.trim().toLowerCase()
  if (!q) return profiles
  return profiles.filter(p =>
    matches(p.userName, q) || matches(p.email, q) || p.modules.some(m => matches(m.name, q)),
  )
}

export function filterAreas(areas: SkillArea[], query: string): SkillArea[] {
  const q = query.trim().toLowerCase()
  if (!q) return areas
  return areas.filter(a => matches(a.name, q) || a.people.some(p => matches(p.userName, q)))
}

/** Bar colour per rank inside a card: the strongest skill takes the action blue. */
const RANK_COLOURS = ['primary', 'brand', 'on-surface-variant'] as const

export function rankColour(index: number): string {
  return RANK_COLOURS[Math.min(index, RANK_COLOURS.length - 1)]
}
