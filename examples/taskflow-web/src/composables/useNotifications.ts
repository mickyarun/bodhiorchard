import { ref, computed } from 'vue'
import api from '@/services/api'
import type { Notification } from '@/types/notification'

const CACHE_KEY = 'notif_cache'

const notifications = ref<Notification[]>([])
const loading = ref(false)
const offline = ref(false)
const toastError = ref<string | null>(null)

export function useNotifications() {
  const unreadCount = computed(() => notifications.value.filter(n => !n.is_read).length)
  const badgeLabel = computed(() =>
    unreadCount.value === 0 ? '' : unreadCount.value > 99 ? '99+' : String(unreadCount.value)
  )
  const hasUnread = computed(() => unreadCount.value > 0)

  function showToast(msg: string) {
    toastError.value = msg
    setTimeout(() => { toastError.value = null }, 3000)
  }

  async function fetchNotifications() {
    loading.value = true
    try {
      const { data } = await api.get<Notification[]>('/notifications')
      notifications.value = data
      offline.value = false
      localStorage.setItem(CACHE_KEY, JSON.stringify(data))
    } catch (err: any) {
      if (!navigator.onLine || err.code === 'ERR_NETWORK') {
        offline.value = true
        const cached = localStorage.getItem(CACHE_KEY)
        if (cached) notifications.value = JSON.parse(cached)
      }
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
      showToast('Failed to mark as read. Please try again.')
    }
  }

  async function markAllRead() {
    const prev = notifications.value.map(n => ({ ...n }))
    notifications.value.forEach(n => { n.is_read = true })
    try {
      await api.post('/notifications/read-all')
    } catch {
      notifications.value = prev
      showToast('Failed to mark all as read. Please try again.')
    }
  }

  async function deleteNotification(id: number) {
    const idx = notifications.value.findIndex(n => n.id === id)
    if (idx === -1) return
    const [removed] = notifications.value.splice(idx, 1)
    try {
      await api.delete(`/notifications/${id}`)
    } catch {
      notifications.value.splice(idx, 0, removed)
      showToast('Failed to delete notification. Please try again.')
    }
  }

  return {
    notifications, loading, offline, toastError,
    unreadCount, badgeLabel, hasUnread,
    fetchNotifications, markRead, markAllRead, deleteNotification,
  }
}
