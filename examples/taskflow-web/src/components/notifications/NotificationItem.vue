<template>
  <div
    class="notification-item"
    :class="{ unread: !notification.is_read }"
  >
    <div class="item-row">
      <span class="type-dot" :class="notification.type" aria-hidden="true"></span>
      <div class="item-content">
        <div class="item-header">
          <span class="item-title">{{ notification.title }}</span>
          <span class="item-time" :title="notification.created_at">{{ relativeTime }}</span>
        </div>
        <p v-if="notification.body" class="item-body">{{ notification.body }}</p>
      </div>
      <div class="item-actions">
        <button
          v-if="!notification.is_read"
          class="action-btn read-btn"
          aria-label="Mark as read"
          @click.stop="store.markRead(notification.id)"
        >
          &#10003;
        </button>
        <button
          class="action-btn delete-btn"
          aria-label="Delete notification"
          @click.stop="store.deleteNotification(notification.id)"
        >
          &times;
        </button>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { useNotificationStore, type Notification } from '@/stores/notifications'

const props = defineProps<{ notification: Notification }>()
const store = useNotificationStore()

const relativeTime = computed(() => {
  const now = Date.now()
  const then = new Date(props.notification.created_at).getTime()
  const diffSec = Math.floor((now - then) / 1000)

  if (diffSec < 60) return 'just now'
  const diffMin = Math.floor(diffSec / 60)
  if (diffMin < 60) return `${diffMin}m ago`
  const diffHr = Math.floor(diffMin / 60)
  if (diffHr < 24) return `${diffHr}h ago`
  const diffDay = Math.floor(diffHr / 24)
  if (diffDay < 30) return `${diffDay}d ago`
  return new Date(props.notification.created_at).toLocaleDateString()
})
</script>

<style scoped>
.notification-item {
  padding: 12px 16px;
  border-bottom: 1px solid #eee;
  transition: background 0.15s;
}
.notification-item.unread {
  background: var(--color-surface-alt, #f5f5f5);
  border-left: 3px solid var(--color-accent, #4f46e5);
}
.notification-item:hover {
  background: #f0f0f0;
}
.item-row {
  display: flex;
  align-items: flex-start;
  gap: 10px;
}
.type-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  margin-top: 6px;
  flex-shrink: 0;
}
.type-dot.task_assigned { background: #4f46e5; }
.type-dot.task_comment { background: #0ea5e9; }
.type-dot.task_status_changed { background: #f59e0b; }
.type-dot.invoice_ready { background: #10b981; }
.type-dot.reminder { background: #8b5cf6; }

.item-content {
  flex: 1;
  min-width: 0;
}
.item-header {
  display: flex;
  justify-content: space-between;
  align-items: baseline;
  gap: 8px;
}
.item-title {
  font-size: 13px;
  font-weight: 500;
  color: var(--color-text, #1a1a2e);
}
.unread .item-title {
  font-weight: 700;
}
.item-time {
  font-size: 11px;
  color: var(--color-text-muted, #6b7280);
  white-space: nowrap;
  flex-shrink: 0;
}
.item-body {
  font-size: 12px;
  color: var(--color-text-muted, #6b7280);
  margin: 4px 0 0;
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
}
.item-actions {
  display: flex;
  gap: 4px;
  flex-shrink: 0;
  opacity: 0;
  transition: opacity 0.15s;
}
.notification-item:hover .item-actions {
  opacity: 1;
}
.action-btn {
  width: 28px;
  height: 28px;
  border: none;
  border-radius: 6px;
  background: transparent;
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 16px;
  color: var(--color-text-muted, #6b7280);
}
.action-btn:hover {
  background: #e5e7eb;
}
.action-btn:focus-visible {
  outline: 2px solid var(--color-accent, #4f46e5);
  outline-offset: 1px;
}
.read-btn:hover {
  color: var(--color-accent, #4f46e5);
}
.delete-btn:hover {
  color: var(--color-danger, #ef4444);
}
</style>
