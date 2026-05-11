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
import type { AppNotification } from '@/types'
import api from '@/services/api'

export const useNotificationStore = defineStore('notifications', () => {
  const items = ref<AppNotification[]>([])
  const loading = ref(false)
  const error = ref('')

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

  return {
    items, loading, error, unreadCount,
    fetchAll, markRead, markAllRead, dismiss, dismissAll, addFromSocket,
  }
})
