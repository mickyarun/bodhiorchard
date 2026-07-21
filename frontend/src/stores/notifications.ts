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

import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import { isAxiosError } from 'axios'
import type { AppNotification } from '@/types'
import api from '@/services/api'

export const useNotificationStore = defineStore('notifications', () => {
  const items = ref<AppNotification[]>([])
  const loading = ref(false)
  const error = ref('')
  /** Notification ids with an in-flight decline POST. Drives the button
   *  disabled state so a double-click can't fire parallel POSTs and
   *  clobber the success state with a 404-on-the-second-call error. */
  const pendingDeclineIds = ref<Set<string>>(new Set())

  const unreadCount = computed(() =>
    items.value.filter(n => !n.isRead && !n.isDismissed).length,
  )

  async function fetchAll(): Promise<void> {
    loading.value = true
    error.value = ''
    try {
      const { data } = await api.get<AppNotification[]>('/v1/notifications/')
      items.value = data
    } catch {
      error.value = 'Failed to load notifications'
    } finally {
      loading.value = false
    }
  }

  async function markRead(id: string): Promise<void> {
    try {
      await api.post(`/v1/notifications/${id}/read`)
      const idx = items.value.findIndex(n => n.id === id)
      if (idx !== -1) items.value[idx].isRead = true
    } catch {
      error.value = 'Failed to mark notification as read'
    }
  }

  async function markAllRead(): Promise<void> {
    try {
      await api.post('/v1/notifications/read-all')
      items.value.forEach(n => { n.isRead = true })
    } catch {
      error.value = 'Failed to mark all as read'
    }
  }

  async function dismiss(id: string): Promise<void> {
    try {
      await api.delete(`/v1/notifications/${id}`)
      items.value = items.value.filter(n => n.id !== id)
    } catch {
      error.value = 'Failed to dismiss notification'
    }
  }

  async function dismissAll(): Promise<void> {
    try {
      await api.delete('/v1/notifications/')
      items.value = []
    } catch {
      error.value = 'Failed to dismiss notifications'
    }
  }

  /** Called by WS composable when a real-time notification arrives. */
  function addFromSocket(notif: AppNotification): void {
    if (!items.value.some(n => n.id === notif.id)) {
      items.value.unshift(notif)
    }
  }

  /**
   * Decline a pending race-invite notification. Distinct from
   * `dismiss` because the server-side handler also writes a fresh
   * notification on the host's bell so they stop waiting on a no-show.
   * Optimistically removes the row on success; on failure the user
   * can retry from the same row since we don't touch it on error.
   */
  async function declineInvite(
    id: string,
    endpoint: string,
    unavailableMessage: string,
    failureMessage: string,
  ): Promise<void> {
    if (pendingDeclineIds.value.has(id)) return
    pendingDeclineIds.value.add(id)
    try {
      await api.post(endpoint)
      items.value = items.value.filter(n => n.id !== id)
    } catch (err) {
      // 404 is the "already declined / not yours" path — the row is
      // stale, drop it locally so the user isn't stuck staring at it.
      // Other failures stay visible so the user can retry.
      const status = isAxiosError(err) ? err.response?.status : undefined
      if (status === 404) {
        items.value = items.value.filter(n => n.id !== id)
        error.value = unavailableMessage
      } else {
        error.value = `${failureMessage}${status ? ` (${status})` : ''}`
      }
    } finally {
      pendingDeclineIds.value.delete(id)
    }
  }

  async function declineRaceInvite(id: string): Promise<void> {
    await declineInvite(
      id,
      `/v1/races/invites/${id}/decline`,
      'Race invite is no longer available',
      'Failed to decline race invite',
    )
  }

  async function declineBacklashInvite(id: string): Promise<void> {
    await declineInvite(
      id,
      `/v1/minigames/backlash/invites/${id}/decline`,
      'Backlash challenge is no longer available',
      'Failed to decline Backlash challenge',
    )
  }

  return {
    items, loading, error, unreadCount, pendingDeclineIds,
    fetchAll, markRead, markAllRead, dismiss, dismissAll, addFromSocket,
    declineRaceInvite, declineBacklashInvite,
  }
})
