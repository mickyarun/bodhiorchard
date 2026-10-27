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
import type { Feature } from '@/types'
import {
  codeLocations,
  codeLocationsText,
  deactivatedSummary,
  featureCapabilities,
  featureDisplayTitle,
  featureHasDetail,
  featureLifecycle,
  featureLineage,
  lineageRow,
  showLastTouched,
} from './featureCard'
import { featureSetupSteps } from './featureSetup'

function feature(over: Partial<Feature> = {}): Feature {
  return {
    id: 'f1', featureTitle: 'Feature: Billing export', description: '', capabilities: {}, clusterNames: [], tags: [],
    featureStatus: null, source: 'scan', sourceRef: null, synthesizedAt: '2026-10-01T00:00:00Z', primary: null,
    backendLinks: [], createdAt: '2026-10-01T00:00:00Z', createdAtSha: 'aaaaaaaaaa', createdPrNumber: null,
    createdPrUrl: null, creationMode: 'full_scan', updatedAt: '2026-10-01T00:00:00Z', lastSeenSha: 'aaaaaaaaaa',
    lastSeenPrNumber: null, lastSeenPrUrl: null, isActive: true, deactivatedAt: null, deactivatedAtSha: null,
    deactivatedPrNumber: null, deactivatedPrUrl: null, ...over,
  }
}

describe('featureCard', () => {
  it('drops the "Feature:" prefix', () => expect(featureDisplayTitle(feature())).toBe('Billing export'))

  it('gives one lifecycle tag, Live for scan rows', () => {
    expect(featureLifecycle(feature())).toEqual({ label: 'Live', color: 'success' })
    expect(featureLifecycle(feature({ featureStatus: 'in_progress' })).label).toBe('In progress')
    expect(featureLifecycle(feature({ isActive: false })).label).toBe('Deactivated')
  })

  it('reads capability strings only', () => {
    expect(featureCapabilities(feature({ capabilities: { capabilities: ['Export', 3] } }))).toEqual(['Export'])
    expect(featureCapabilities(feature())).toEqual([])
  })

  it('prefers the PR, then the BUD, then the SHA', () => {
    expect(lineageRow(5, 'u', 'abc', null, 'BUD-001')).toEqual({ byLabel: 'PR #5', prUrl: 'u' })
    expect(lineageRow(null, null, 'abcdef123', null, 'BUD-001').byLabel).toBe('BUD-001')
    expect(lineageRow(null, null, 'abcdef123', 'baseline scan', null).byLabel).toBe('baseline scan (abcdef1)')
    expect(lineageRow(null, null, 'abcdef123', null, null).byLabel).toBe('commit abcdef1')
    expect(lineageRow(null, null, null, null, null).byLabel).toBeNull()
  })

  it('builds created and last-touched lineage', () => {
    const l = featureLineage(feature({ source: 'bud', sourceRef: 'BUD-021', lastSeenPrNumber: 9, lastSeenPrUrl: 'p' }))
    expect(l.created.byLabel).toBe('BUD-021')
    expect(l.lastSeen).toEqual({ byLabel: 'PR #9', prUrl: 'p' })
  })

  it('hides last touched for untouched rows', () => {
    expect(showLastTouched(feature())).toBe(false)
    expect(showLastTouched(feature({ lastSeenSha: 'bbbbbbb', updatedAt: '2026-10-02T00:00:00Z' }))).toBe(true)
  })

  it('summarises deactivation with a SHA fallback', () => {
    expect(deactivatedSummary(feature())).toBeNull()
    const s = deactivatedSummary(feature({ isActive: false, deactivatedAt: '2026-10-05T12:00:00Z', deactivatedAtSha: '1234567890' }))
    expect(s).toEqual({ dateLabel: 'Oct 5, 2026', prNumber: null, prUrl: null, shortSha: '1234567' })
  })

  it('offers details only when there are some', () => {
    expect(featureHasDetail(feature())).toBe(false)
    expect(featureHasDetail(feature({ description: 'x'.repeat(201) }))).toBe(true)
    expect(featureHasDetail(feature({ capabilities: { capabilities: ['Export'] } }))).toBe(true)
  })

  it('merges code locations by layer', () => {
    const f = feature({
      primary: { repoId: 'r', repoName: 'web', codeLocations: { ui: ['b.ts', 'a.ts'] } },
      backendLinks: [{ repoId: 's', repoName: 'api', apiPaths: [], codeLocations: { ui: ['a.ts'], api: ['x.py'] } }],
    })
    const locs = codeLocations(f)
    expect([...locs]).toEqual([['ui', ['a.ts', 'b.ts']], ['api', ['x.py']]])
    expect(codeLocationsText(locs)).toBe('# ui\na.ts\nb.ts\n\n# api\nx.py')
  })
})

describe('featureSetupSteps', () => {
  const states = (repos: Parameters<typeof featureSetupSteps>[0]): string[] => featureSetupSteps(repos).map(s => s.state)

  it('starts at connecting a repository', () => expect(states([])).toEqual(['next', 'then', 'then']))
  it('moves to the scan once a repository is connected', () => {
    expect(states([{ status: 'active', lastScanned: null }])).toEqual(['done', 'next', 'then'])
  })
  it('ignores removed repositories', () => {
    expect(states([{ status: 'removed', lastScanned: '2026-10-01' }])).toEqual(['next', 'then', 'then'])
  })
  it('points at the map after a scan', () => {
    expect(states([{ status: 'active', lastScanned: '2026-10-01' }])).toEqual(['done', 'done', 'next'])
  })
})
