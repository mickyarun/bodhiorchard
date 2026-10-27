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
import type { ConnectionsState } from '@/stores/settings'
import { differsFrom, pickSections, snapshotSection } from './connectionSections'

const state = {
  slack: { enabled: true, connected: true, botToken: 'xoxb-****', signingSecret: '', teamId: 'T1' },
  presence: { autoModeEnabled: true, workingDays: ['mon'], workingHoursStart: '08:00', workingHoursEnd: '18:00', timezone: null },
} as unknown as ConnectionsState

describe('pickSections', () => {
  it('keeps only the named sections', () => {
    expect(pickSections(state, ['slack'])).toEqual({ slack: state.slack })
  })
})

describe('snapshotSection and differsFrom', () => {
  it('copies deeply so later edits show as changes', () => {
    const snap = snapshotSection(state, 'presence')
    expect(differsFrom(state.presence, snap)).toBe(false)
    state.presence.workingDays.push('tue')
    expect(differsFrom(state.presence, snap)).toBe(true)
    expect(snap.workingDays).toEqual(['mon'])
  })
})
