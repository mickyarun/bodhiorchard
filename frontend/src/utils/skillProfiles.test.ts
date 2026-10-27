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
import type { ModuleSkill, SkillProfile } from '@/types'
import {
  filterAreas,
  filterProfiles,
  groupByArea,
  profileSummary,
  scorePercent,
  skillLevel,
  sortByScore,
  topLevelArea,
} from './skillProfiles'

function mod(name: string, score: number, touchCount: number, languages = ['Python']): ModuleSkill {
  return { name, score, touchCount, languages, linesAdded: 0, linesRemoved: 0 }
}

const meera: SkillProfile = {
  userId: 'u1',
  userName: 'Meera Iyer',
  email: 'meera@example.com',
  modules: [mod('payments/refunds', 0.92, 64), mod('auth/two_factor', 0.5, 10), mod('payments/ledger', 0.3, 6)],
}
const ravi: SkillProfile = {
  userId: 'u2',
  userName: 'Ravi Kumar',
  email: 'ravi@example.com',
  modules: [mod('auth/two_factor', 0.8, 30, ['TypeScript']), mod('web/portal', 0.6, 30)],
}

describe('skillLevel', () => {
  it('maps score bands to words', () => {
    expect(skillLevel(0.75)).toBe('Expert')
    expect(skillLevel(0.74)).toBe('Strong')
    expect(skillLevel(0.45)).toBe('Strong')
    expect(skillLevel(0.1)).toBe('Familiar')
  })
})

describe('scorePercent', () => {
  it('rounds and clamps', () => {
    expect(scorePercent(0.926)).toBe(93)
    expect(scorePercent(1.4)).toBe(100)
    expect(scorePercent(-1)).toBe(0)
  })
})

describe('sortByScore', () => {
  it('sorts strongest first without mutating', () => {
    const input = [{ score: 0.2 }, { score: 0.9 }]
    expect(sortByScore(input).map(i => i.score)).toEqual([0.9, 0.2])
    expect(input[0].score).toBe(0.2)
  })
})

describe('profileSummary', () => {
  it('names the area holding most commits', () => {
    expect(profileSummary(meera.modules)).toBe('Mostly in payments · 80 commits')
  })
  it('falls back to an area count when nothing dominates', () => {
    expect(profileSummary(ravi.modules)).toBe('Across 2 areas · 60 commits')
  })
  it('reads cleanly with a single commit', () => {
    expect(profileSummary([mod('api', 0.4, 1)])).toBe('Mostly in api · 1 commit')
  })
})

describe('topLevelArea', () => {
  it('takes the first path segment', () => {
    expect(topLevelArea('payments/refunds')).toBe('payments')
    expect(topLevelArea('api')).toBe('api')
  })
})

describe('groupByArea', () => {
  it('collects people per module, strongest first, shared areas first', () => {
    const areas = groupByArea([meera, ravi])
    expect(areas[0].name).toBe('auth/two_factor')
    expect(areas[0].people.map(p => p.userName)).toEqual(['Ravi Kumar', 'Meera Iyer'])
    expect(areas[0].languages).toEqual(['Python', 'TypeScript'])
    expect(areas).toHaveLength(4)
  })
})

describe('filters', () => {
  it('matches people by name, email or module', () => {
    expect(filterProfiles([meera, ravi], 'portal')).toEqual([ravi])
    expect(filterProfiles([meera, ravi], 'MEERA@')).toEqual([meera])
    expect(filterProfiles([meera, ravi], '  ')).toHaveLength(2)
  })
  it('matches areas by name or person', () => {
    const areas = groupByArea([meera, ravi])
    expect(filterAreas(areas, 'ravi').map(a => a.name)).toEqual(['auth/two_factor', 'web/portal'])
    expect(filterAreas(areas, 'ledger').map(a => a.name)).toEqual(['payments/ledger'])
  })
})
