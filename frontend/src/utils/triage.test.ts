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
import type { TriageSession } from '@/stores/triage'
import { contextFacts, isCompliance, requesterName, triageStatus } from './triage'

function session(over: Partial<TriageSession> = {}): TriageSession {
  return {
    id: 's1', org_id: 'o', slack_channel: 'C1', thread_ts: '1.2', requester_slack_id: 'U1', requester_name: null,
    requester_display_name: null, original_text: 'Please add export', status: 'awaiting_pm', priority: null, bud_priority: 'P2',
    feature_name: 'Export', triage_context: null, bud_id: null, created_at: '2026-10-01T00:00:00Z',
    updated_at: '2026-10-01T00:00:00Z', ...over,
  }
}

describe('triage', () => {
  it('names the requester from the best source', () => {
    expect(requesterName(session({ requester_display_name: 'Emma Clarke', requester_name: 'emma' }))).toBe('Emma Clarke')
    expect(requesterName(session({ requester_name: 'emma' }))).toBe('emma')
    expect(requesterName(session({ requester_name: 'U1' }))).toBe('U1')
  })

  it('labels statuses, passing unknown ones through', () => {
    expect(triageStatus('bud_created')).toEqual({ label: 'BUD created', color: 'success' })
    expect(triageStatus('mystery').label).toBe('mystery')
  })

  it('lists the gathered context as labelled facts', () => {
    const ctx = { urgency: 'This quarter', business_justification: ' Three customers asked ', compliance: true, user_impact: '' }
    expect(contextFacts(ctx)).toEqual([
      { label: 'Why', value: 'Three customers asked' },
      { label: 'Urgency', value: 'This quarter' },
    ])
    expect(isCompliance(ctx)).toBe(true)
    expect(contextFacts(null)).toEqual([])
    expect(isCompliance(null)).toBe(false)
  })
})
