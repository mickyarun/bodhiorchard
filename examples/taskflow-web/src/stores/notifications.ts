import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import api from '@/services/api'

export interface Notification {
  id: number
  type: 'task_assigned' | 'task_comment' | 'task_status_changed' | 'invoice_ready' | 'reminder'
  title: string
  body: string
  is_read: boolean
  link: string | null
  created_at: string
}

export const useNotificationStore = defineStore('notifications', () => {
  const notifications = ref<Notification[]>([])
  const loading = ref(false)
  const error = ref<string | null>(null)

  const unreadCount = computed(() => notifications.value.filter(n => !n.is_read).length)
  const hasUnread = computed(() => unreadCount.value > 0)
  const badgeLabel = computed(() => unreadCount.value > 99 ? '99+' : String(unreadCount.value))

  async function fetchNotifications() {
    loading.value = true
    error.value = null
    try {
      const { data } = await api.get<Notification[]>('/notifications')
      notifications.value = data
    } catch {
      error.value = 'Failed to load notifications'
    } finally {
      loading.value = false
    }
  }

  async function markRead(id: number) {
    const notif = notifications.value.find(n => n.id === id)
    if (!notif || notif.is_read) return

    notif.is_read = true
    try {
      await api.patch(`/notifications/${id}/read`)
    } catch {
      notif.is_read = false
    }
  }

  async function markAllRead() {
    const previousStates = notifications.value
      .filter(n => !n.is_read)
      .map(n => ({ id: n.id, is_read: n.is_read }))

    notifications.value.forEach(n => { n.is_read = true })
    try {
      await api.post('/notifications/read-all')
    } catch {
      previousStates.forEach(prev => {
        const notif = notifications.value.find(n => n.id === prev.id)
        if (notif) notif.is_read = prev.is_read
      })
    }
  }

  async function deleteNotification(id: number) {
    const index = notifications.value.findIndex(n => n.id === id)
    if (index === -1) return

    const removed = notifications.value.splice(index, 1)[0]
    try {
      await api.delete(`/notifications/${id}`)
    } catch {
      notifications.value.splice(index, 0, removed)
    }
  }

  return {
    notifications,
    loading,
    error,
    unreadCount,
    hasUnread,
    badgeLabel,
    fetchNotifications,
    markRead,
    markAllRead,
    deleteNotification,
  }
})
