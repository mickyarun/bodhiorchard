import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import api from '@/services/api'
import type { Notification } from '@/types/notification'

interface ApiNotification {
  id: number
  type: string
  title: string
  body: string
  time: string
  is_read: boolean
  is_dismissed: boolean
}

function toNotification(raw: ApiNotification): Notification {
  return {
    id: raw.id,
    type: raw.type as Notification['type'],
    title: raw.title,
    body: raw.body ?? '',
    time: raw.time ?? '',
    isRead: raw.is_read,
    isDismissed: raw.is_dismissed ?? false,
  }
}

export const useNotificationStore = defineStore('notifications', () => {
  const items = ref<Notification[]>([])
  const loading = ref(false)
  const error = ref('')

  const unreadCount = computed(() =>
    items.value.filter(n => !n.isRead && !n.isDismissed).length,
  )

  const visibleItems = computed(() =>
    items.value.filter(n => !n.isDismissed),
  )

  async function fetchAll() {
    loading.value = true
    error.value = ''
    try {
      const { data } = await api.get<ApiNotification[]>('/notifications')
      items.value = data.map(toNotification)
    } catch {
      error.value = 'Failed to load notifications.'
    } finally {
      loading.value = false
    }
  }

  async function markRead(id: number) {
    const item = items.value.find(n => n.id === id)
    if (!item || item.isRead) return

    item.isRead = true
    try {
      await api.patch(`/notifications/${id}/read`)
    } catch {
      item.isRead = false
      error.value = 'Failed to mark as read. Unread highlight restored.'
    }
  }

  async function markAllRead() {
    const unread = items.value.filter(n => !n.isRead)
    unread.forEach(n => { n.isRead = true })
    try {
      await api.patch('/notifications/read-all')
    } catch {
      unread.forEach(n => { n.isRead = false })
      error.value = 'Failed to mark all as read.'
    }
  }

  async function dismiss(id: number) {
    const idx = items.value.findIndex(n => n.id === id)
    if (idx === -1) return

    const removed = items.value.splice(idx, 1)[0]
    try {
      await api.delete(`/notifications/${id}`)
    } catch {
      items.value.splice(idx, 0, removed)
      error.value = 'Failed to dismiss notification.'
    }
  }

  async function dismissAll() {
    const backup = [...items.value]
    items.value = []
    try {
      await api.delete('/notifications')
    } catch {
      items.value = backup
      error.value = 'Failed to clear notifications.'
    }
  }

  function addItem(notification: Notification) {
    items.value.unshift(notification)
  }

  return {
    items,
    visibleItems,
    loading,
    error,
    unreadCount,
    fetchAll,
    markRead,
    markAllRead,
    dismiss,
    dismissAll,
    addItem,
  }
})
