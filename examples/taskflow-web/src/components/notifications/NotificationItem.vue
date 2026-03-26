<template>
  <div
    class="notif-item"
    :class="{ unread: !notification.is_read }"
    role="listitem"
    tabindex="0"
  >
    <div class="notif-avatar" :class="`type-${avatarClass}`">{{ initials }}</div>

    <div class="notif-body">
      <p class="notif-msg">{{ notification.title }}</p>
      <p v-if="notification.body" class="notif-sub">{{ notification.body }}</p>
      <span class="notif-time">{{ timeAgo(notification.created_at) }}</span>
    </div>

    <div class="notif-dot" v-if="!notification.is_read" aria-hidden="true" />

    <div class="notif-actions">
      <button
        v-if="!notification.is_read"
        class="action-btn"
        title="Mark as read"
        aria-label="Mark as read"
        @click.stop="emit('mark-read', notification.id)"
      >
        <svg width="16" height="16" viewBox="0 0 16 16" fill="none" aria-hidden="true">
          <path d="M2.5 8.5L6 12L13.5 4" stroke="currentColor" stroke-width="1.75" stroke-linecap="round" stroke-linejoin="round"/>
        </svg>
      </button>
      <button
        class="action-btn action-delete"
        title="Delete"
        aria-label="Delete notification"
        @click.stop="emit('delete', notification.id)"
      >
        <svg width="16" height="16" viewBox="0 0 16 16" fill="none" aria-hidden="true">
          <path d="M3 4h10M6 4V2.5h4V4M5 4v8.5a.5.5 0 0 0 .5.5h5a.5.5 0 0 0 .5-.5V4" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"/>
        </svg>
      </button>
    </div>
  </div>
</template>

<script setup lang="ts">
import type { Notification } from '@/types/notification'

const props = defineProps<{ notification: Notification }>()
const emit = defineEmits<{ 'mark-read': [id: number]; 'delete': [id: number] }>()

const avatarClassMap: Record<Notification['type'], string> = {
  task_assigned: 'task',
  task_comment: 'comment',
  task_status_changed: 'system',
  invoice_ready: 'system',
  reminder: 'mention',
}
const avatarClass = avatarClassMap[props.notification.type] ?? 'system'

const initials = props.notification.title
  .split(' ')
  .slice(0, 2)
  .map(w => w[0]?.toUpperCase() ?? '')
  .join('')

function timeAgo(iso: string | null): string {
  // TODO: Implement relative time display.
  // The diff variable below gives you milliseconds since the notification was created.
  // Thresholds to consider: just now (<1m), Xm ago (<1h), Xh ago (<24h), Xd ago (else)
  // Optional: show actual date for items older than 7 days (e.g. "Mar 19") for clarity.
  if (!iso) return ''
  const diff = Date.now() - new Date(iso).getTime()
  if (diff < 60_000) return 'just now'
  if (diff < 3_600_000) return `${Math.floor(diff / 60_000)}m ago`
  if (diff < 86_400_000) return `${Math.floor(diff / 3_600_000)}h ago`
  return `${Math.floor(diff / 86_400_000)}d ago`
}
</script>

<style scoped>
.notif-item {
  display: flex;
  align-items: flex-start;
  gap: 10px;
  padding: 12px 16px;
  border-bottom: 1px solid #f0f0f0;
  cursor: default;
  position: relative;
  transition: background 0.15s;
}
.notif-item:hover { background: var(--color-hover-bg, #f5f7fa); }
.notif-item.unread { background: var(--color-unread-bg, #f0f4ff); }
.notif-item:focus-visible { outline: 2px solid #1a1a2e; outline-offset: -2px; }

.notif-avatar {
  flex-shrink: 0;
  width: 36px;
  height: 36px;
  border-radius: 50%;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 12px;
  font-weight: 700;
  color: #fff;
}
.type-task    { background: var(--color-brand, #1a1a2e); }
.type-comment { background: var(--color-success, #2e7d32); }
.type-system  { background: #6a6a9a; }
.type-mention { background: var(--color-warning, #f57c00); }

.notif-body { flex: 1; min-width: 0; }
.notif-msg {
  margin: 0 0 2px;
  font-size: 13px;
  font-weight: 500;
  line-height: 1.4;
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
}
.notif-item.unread .notif-msg { font-weight: 600; }
.notif-sub {
  margin: 0 0 4px;
  font-size: 12px;
  color: #555;
  display: -webkit-box;
  -webkit-line-clamp: 1;
  -webkit-box-orient: vertical;
  overflow: hidden;
}
.notif-time { font-size: 11px; color: var(--color-muted, #757575); }

.notif-dot {
  flex-shrink: 0;
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: var(--color-brand, #1a1a2e);
  margin-top: 6px;
}

.notif-actions {
  display: flex;
  gap: 4px;
  opacity: 0;
  transition: opacity 0.15s;
  flex-shrink: 0;
}
.notif-item:hover .notif-actions,
.notif-item:focus-within .notif-actions { opacity: 1; }

.action-btn {
  width: 28px;
  height: 28px;
  border: none;
  background: transparent;
  border-radius: 6px;
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  color: var(--color-muted, #757575);
  padding: 0;
  transition: background 0.12s, color 0.12s;
}
.action-btn:hover { background: #e8eaf6; color: #1a1a2e; }
.action-delete:hover { background: #fde8e8; color: var(--color-danger, #c62828); }
</style>
