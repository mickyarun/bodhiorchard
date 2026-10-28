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
import type { AppNotification } from '@/types'
import { declinableInvite, notificationVisual } from './notificationVisuals'

function notif(over: Partial<AppNotification>): AppNotification {
  return {
    id: 'n1', type: 'job_completed', jobId: null, jobType: null, title: 't', message: null,
    deepLink: null, isRead: false, isDismissed: false, createdAt: '2026-10-28T00:00:00Z', ...over,
  }
}

const LATER = new Date(Date.now() + 60 * 60 * 1000).toISOString()
const EARLIER = new Date(Date.now() - 60 * 1000).toISOString()

describe('notificationVisual', () => {
  it('gives each type its own icon, with status tone only where it means something', () => {
    expect(notificationVisual('leave_requested')).toEqual({ icon: 'mdi-calendar-account-outline', tone: 'warning' })
    expect(notificationVisual('job_failed').tone).toBe('error')
    expect(notificationVisual('race_invite').tone).toBe('neutral')
  })

  it('falls back to a plain bell for a type the frontend does not know yet', () => {
    expect(notificationVisual('something_new')).toEqual({ icon: 'mdi-bell-outline', tone: 'neutral' })
  })
})

describe('declinableInvite', () => {
  it('lets an invitee decline an open race invite', () => {
    expect(declinableInvite(notif({ type: 'race_invite', meta: { hostUserId: 'host' } }), 'me')).toBe('race')
  })

  it('never offers decline on the host side or once declined', () => {
    expect(declinableInvite(notif({ type: 'race_invite', meta: { hostUserId: 'me' } }), 'me')).toBeNull()
    expect(declinableInvite(notif({ type: 'race_invite', meta: { hostUserId: 'h', declinedBy: 'x' } }), 'me')).toBeNull()
  })

  it('offers decline on a backlash invite only until it expires', () => {
    const meta = { game: 'backlash', hostUserId: 'host', expiresAt: LATER }
    expect(declinableInvite(notif({ type: 'minigame_invite', meta }), 'me')).toBe('backlash')
    expect(declinableInvite(notif({ type: 'minigame_invite', meta: { ...meta, expiresAt: EARLIER } }), 'me')).toBeNull()
  })

  it('has nothing to decline on other types', () => {
    expect(declinableInvite(notif({ type: 'leave_requested' }), 'me')).toBeNull()
  })
})
