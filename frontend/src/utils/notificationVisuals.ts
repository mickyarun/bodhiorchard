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

/** How a notification looks in the tray: its icon, and a status tone. */
import type { AppNotification, BacklashInviteMeta, NotificationType, RaceInviteMeta } from '@/types'
import { isInviteUnexpired } from '@/utils/inviteExpiry'

/**
 * Status tone for the icon's container. neutral is for plain news;
 * the others are status colours and only mean what they say: something
 * failed, something waits on you, something went through, a hand-off.
 */
export type NotificationTone = 'neutral' | 'info' | 'warning' | 'error' | 'success'

export interface NotificationVisual {
  icon: string
  tone: NotificationTone
}

const VISUALS: Record<NotificationType, NotificationVisual> = {
  job_completed: { icon: 'mdi-robot-outline', tone: 'neutral' },
  job_failed: { icon: 'mdi-alert-circle-outline', tone: 'error' },
  approval_requested: { icon: 'mdi-account-clock-outline', tone: 'warning' },
  approval_granted: { icon: 'mdi-check-decagram-outline', tone: 'success' },
  approval_rejected: { icon: 'mdi-close-octagon-outline', tone: 'error' },
  developer_assigned: { icon: 'mdi-account-arrow-right-outline', tone: 'info' },
  reassignment_done: { icon: 'mdi-swap-horizontal', tone: 'info' },
  testing_ready: { icon: 'mdi-test-tube', tone: 'info' },
  pr_opened: { icon: 'mdi-source-pull', tone: 'neutral' },
  pr_merged: { icon: 'mdi-source-merge', tone: 'success' },
  all_prs_merged: { icon: 'mdi-source-merge', tone: 'success' },
  race_invite: { icon: 'mdi-flag-checkered', tone: 'neutral' },
  minigame_invite: { icon: 'mdi-gamepad-variant-outline', tone: 'neutral' },
  leave_requested: { icon: 'mdi-calendar-account-outline', tone: 'warning' },
  leave_decided: { icon: 'mdi-calendar-check-outline', tone: 'neutral' },
  employee_record_changed: { icon: 'mdi-card-account-details-outline', tone: 'neutral' },
}

const FALLBACK: NotificationVisual = { icon: 'mdi-bell-outline', tone: 'neutral' }

/** The icon and tone for a notification type; a plain bell for new types. */
export function notificationVisual(type: string): NotificationVisual {
  return VISUALS[type as NotificationType] ?? FALLBACK
}

/** Which game invite, if any, the viewer can still decline from this row. */
export type DeclinableInvite = 'race' | 'backlash'

/**
 * A race invite can be declined by an invitee until someone declines it;
 * the host's own "X declined" rows carry `declinedBy` and can't be. A
 * backlash invite also expires. Nobody declines their own invite.
 */
export function declinableInvite(notif: AppNotification, viewerId: string): DeclinableInvite | null {
  if (notif.type === 'race_invite') {
    const meta = (notif.meta ?? {}) as RaceInviteMeta
    return !meta.declinedBy && !!meta.hostUserId && meta.hostUserId !== viewerId ? 'race' : null
  }
  if (notif.type === 'minigame_invite') {
    const meta = (notif.meta ?? {}) as BacklashInviteMeta
    const open = meta.game === 'backlash' && !!meta.hostUserId && !meta.declinedBy
      && isInviteUnexpired(meta.expiresAt) && meta.hostUserId !== viewerId
    return open ? 'backlash' : null
  }
  return null
}
