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
import type { SetupChecklistStatus } from '@/types/setup'
import { setupChecklistItems, setupPollingDone } from './setupChecklist'

const fresh: SetupChecklistStatus = {
  orgCreated: true, claudeCodeTested: false, repoAdded: false, scanComplete: false,
  scanInProgress: false, scanId: null, scanProgress: 0, githubConnected: false,
  slackConnected: false, branchesMapped: false, membersImported: false, qaConfigured: false,
}

describe('setupChecklistItems', () => {
  it('lists nine steps in order, with the optional ones marked', () => {
    const steps = setupChecklistItems(fresh, false)
    expect(steps.map(s => s.key)).toEqual(
      ['org', 'claude', 'repo', 'scan', 'branches', 'github', 'slack', 'members', 'qa'])
    expect(steps.filter(s => s.optional).map(s => s.key)).toEqual(['github', 'slack', 'members', 'qa'])
  })

  it('names the permission each step page needs', () => {
    const byKey = Object.fromEntries(setupChecklistItems(fresh, false).map(s => [s.key, s]))
    expect(byKey.repo.permission).toBe('integrations:configure')
    expect(byKey.members.permission).toBe('team:manage')
    expect(byKey.scan.route).toBeUndefined()
  })

  it('marks the scan as running', () => {
    expect(setupChecklistItems(fresh, true).find(s => s.key === 'scan')?.inProgress).toBe(true)
  })
})

describe('setupPollingDone', () => {
  const ready = { ...fresh, repoAdded: true, scanComplete: true, branchesMapped: true }

  it('stops once the scan steps are done, even without the Claude Code check', () => {
    expect(setupPollingDone(ready)).toBe(true)
  })

  it('keeps polling while a scan runs or a scan step is missing', () => {
    expect(setupPollingDone({ ...ready, scanInProgress: true })).toBe(false)
    expect(setupPollingDone({ ...ready, branchesMapped: false })).toBe(false)
  })
})
