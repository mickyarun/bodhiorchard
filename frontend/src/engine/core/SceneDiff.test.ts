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
import { classifyDiff } from './SceneDiff'
import type { EngineData, EngineRepoData, EngineMember } from '../types'

function repo(name: string, overrides: Partial<EngineRepoData> = {}): EngineRepoData {
  return {
    repo_name: name,
    repo_path: `/repos/${name}`,
    branches: [],
    total_files: 10,
    total_commits: 100,
    health: 'healthy' as EngineRepoData['health'],
    growth_stage: 'mature',
    ...overrides,
  }
}

function member(id: string, overrides: Partial<EngineMember> = {}): EngineMember {
  return {
    user_id: id,
    name: `User ${id}`,
    email: `${id}@example.test`,
    avatar_url: null,
    care_pct: 50,
    top_modules: [],
    character_model: null,
    ...overrides,
  }
}

function baseData(): EngineData {
  return {
    repos: [repo('alpha'), repo('beta')],
    features: [
      { title: 'login', status: 'implemented', source_ref: null, branch_name: null, repo_name: 'alpha', from_bud: null, linked_repos: [], code_locations: null },
    ],
    buds: [],
    threats: [],
    members: [member('u1'), member('u2')],
    agent_activity: [],
    relationships: [
      { source_branch: 'main', target_branch: 'main', source_repo: 'alpha', target_repo: 'beta', rel_type: 'CALLS' as EngineData['relationships'][0]['rel_type'], weight: 1 },
    ],
    feature_skills: [],
  }
}

function clone(data: EngineData): EngineData {
  return JSON.parse(JSON.stringify(data)) as EngineData
}

describe('classifyDiff', () => {
  it('returns none for identical payloads', () => {
    expect(classifyDiff(baseData(), clone(baseData()))).toEqual({ kind: 'none' })
  })

  it('returns none when only garden-irrelevant fields change (buds/threats/feature_skills/agents)', () => {
    const next = clone(baseData())
    next.buds.push({ bud_number: 1, title: 'b', status: 'bud' as EngineData['buds'][0]['status'], branch_name: null, repo_name: 'alpha' })
    next.agent_activity.push({
      agent_name: 'triage', action: 'run', timestamp: 't', status: 'ok',
      skill_slug: 's', repo_name: null, bud_number: null, session_id: null,
      event_type: 'e', task_id: null, bud_title: null, impacted_repo_names: [],
    })
    expect(classifyDiff(baseData(), next)).toEqual({ kind: 'none' })
  })

  it('is insensitive to object key order', () => {
    const next = clone(baseData())
    // Rebuild a repo row with reversed key insertion order
    const r = next.repos[0]
    next.repos[0] = Object.fromEntries(Object.entries(r).reverse()) as unknown as EngineRepoData
    expect(classifyDiff(baseData(), next)).toEqual({ kind: 'none' })
  })

  it('full on repo count change', () => {
    const next = clone(baseData())
    next.repos.push(repo('gamma'))
    expect(classifyDiff(baseData(), next)).toMatchObject({ kind: 'full', reason: 'repo count changed' })
  })

  it('full on repo rename/reorder', () => {
    const next = clone(baseData())
    next.repos.reverse()
    expect(classifyDiff(baseData(), next)).toMatchObject({ kind: 'full', reason: 'repo set/order changed' })
  })

  it('full on any member change (tier upgrade)', () => {
    const next = clone(baseData())
    next.members[0].house_level = 3
    expect(classifyDiff(baseData(), next)).toMatchObject({ kind: 'full', reason: 'members changed' })
  })

  it('full on unknown EngineData fields', () => {
    const next = clone(baseData()) as EngineData & { brand_new_field?: number }
    next.brand_new_field = 1
    expect(classifyDiff(baseData(), next)).toMatchObject({ kind: 'full' })
  })

  it('incremental when one repo health changes', () => {
    const next = clone(baseData())
    next.repos[0].health = 'wilting' as EngineRepoData['health']
    expect(classifyDiff(baseData(), next)).toEqual({
      kind: 'incremental', changedRepos: ['alpha'], relationshipsChanged: false,
    })
  })

  it('incremental when a feature flips status, attributed to its repo', () => {
    const next = clone(baseData())
    next.features[0].status = 'in_progress'
    expect(classifyDiff(baseData(), next)).toEqual({
      kind: 'incremental', changedRepos: ['alpha'], relationshipsChanged: false,
    })
  })

  it('ignores backend shadow features (arc seeds, not tree content)', () => {
    const next = clone(baseData())
    next.features.push({
      title: 'shadow', status: 'implemented', source_ref: null, branch_name: null,
      repo_name: 'beta', from_bud: null, linked_repos: ['alpha', 'beta'],
      code_locations: null, link_role: 'backend',
    })
    expect(classifyDiff(baseData(), next)).toEqual({ kind: 'none' })
  })

  it('incremental with relationshipsChanged when relationships differ', () => {
    const next = clone(baseData())
    next.relationships[0].weight = 5
    expect(classifyDiff(baseData(), next)).toEqual({
      kind: 'incremental', changedRepos: [], relationshipsChanged: true,
    })
  })

  it('treats relationship row order as irrelevant', () => {
    const prev = baseData()
    prev.relationships.push({
      source_branch: 'dev', target_branch: 'dev', source_repo: 'beta',
      target_repo: 'alpha', rel_type: 'IMPORTS' as EngineData['relationships'][0]['rel_type'], weight: 2,
    })
    const next = clone(prev)
    next.relationships.reverse()
    expect(classifyDiff(prev, next)).toEqual({ kind: 'none' })
  })
})
