<template>
  <div class="notif-panel" role="dialog" aria-label="Notifications" aria-modal="true">
    <div class="panel-header">
      <span class="panel-title">Notifications</span>
      <div class="panel-actions">
        <button @click="store.markAllRead()" :disabled="store.unreadCount === 0">
          Mark all read
        </button>
        <template v-if="!showClearConfirm">
          <button class="danger-action" @click="showClearConfirm = true">Clear all</button>
        </template>
        <template v-else>
          <div class="confirm-row" role="group" aria-label="Confirm clear all notifications">
            <span class="confirm-label">Sure?</span>
            <button class="confirm-yes" @click="handleClear" aria-label="Yes, clear all notifications">Yes</button>
            <button class="confirm-no" @click="showClearConfirm = false" aria-label="Cancel, keep notifications">No</button>
          </div>
        </template>
      </div>
    </div>

    <div class="notif-list" role="list">
      <div
        v-for="n in store.visibleItems"
        :key="n.id"
        class="notif-item"
        :class="{ unread: !n.isRead }"
        role="listitem"
        tabindex="0"
      >
        <span class="type-dot" :class="n.type" aria-hidden="true"></span>
        <div class="notif-content">
          <div class="notif-title">{{ n.title }}</div>
          <div class="notif-body">{{ n.body }}</div>
          <time class="notif-time">{{ n.time }}</time>
        </div>
        <div class="notif-actions" role="group" :aria-label="'Actions for: ' + n.title">
          <button
            v-if="!n.isRead"
            class="action-btn mark-read"
            @click.stop="store.markRead(n.id)"
            title="Mark as read"
            :aria-label="'Mark as read: ' + n.title"
          >✓</button>
          <button
            class="action-btn dismiss"
            @click.stop="store.dismiss(n.id)"
            title="Dismiss"
            :aria-label="'Dismiss: ' + n.title"
          >×</button>
        </div>
      </div>

      <div
        v-if="store.visibleItems.length === 0 && !store.loading"
        class="empty-state"
        role="status"
        aria-live="polite"
      >
        <span class="empty-icon" aria-hidden="true">✓</span>
        <p class="empty-label">You're all caught up</p>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref } from 'vue'
import { useNotificationStore } from '@/stores/notifications'

const emit = defineEmits<{ close: [] }>()
const store = useNotificationStore()
const showClearConfirm = ref(false)

async function handleClear() {
  await store.dismissAll()
  showClearConfirm.value = false
  emit('close')
}

defineExpose({ resetConfirm: () => { showClearConfirm.value = false } })
</script>

<style scoped>
.notif-panel {
  position: absolute;
  top: calc(100% + 8px);
  right: 0;
  width: 380px;
  max-height: 480px;
  background: var(--color-surface, #ffffff);
  border-radius: var(--radius-panel, 12px);
  box-shadow: var(--shadow-panel, 0 8px 32px rgba(0, 0, 0, 0.12));
  border: 1px solid #e5e7eb;
  display: flex;
  flex-direction: column;
  overflow: hidden;
  z-index: 1000;
}

.panel-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 12px 16px;
  border-bottom: 1px solid #e5e7eb;
  flex-shrink: 0;
}
.panel-title { font-size: 15px; font-weight: 700; color: var(--color-text, #1a1a2e); }
.panel-actions { display: flex; align-items: center; gap: 6px; }
.panel-actions > button {
  font-size: 12px;
  font-weight: 500;
  color: var(--color-accent, #4f46e5);
  padding: 4px 8px;
  border-radius: 6px;
  border: none;
  background: none;
  cursor: pointer;
  transition: background 0.15s;
}
.panel-actions > button:hover { background: #f0f0ff; }
.panel-actions > button:disabled { opacity: 0.35; cursor: not-allowed; }
.panel-actions > button.danger-action { color: var(--color-danger, #ef4444); }
.panel-actions > button.danger-action:hover { background: #fef2f2; }

.confirm-row { display: flex; align-items: center; gap: 4px; }
.confirm-label { font-size: 12px; color: var(--color-text-muted, #6b7280); margin-right: 2px; }
.confirm-row button {
  font-size: 12px; font-weight: 500; padding: 3px 8px;
  border-radius: 6px; border: none; cursor: pointer;
}
.confirm-yes { background: var(--color-danger, #ef4444); color: #fff; }
.confirm-yes:hover { opacity: 0.88; }
.confirm-no { background: none; color: var(--color-text-muted, #6b7280); }
.confirm-no:hover { background: var(--color-surface-alt, #f5f5f5); }

.notif-list { overflow-y: auto; flex: 1; }

.notif-item {
  display: flex;
  align-items: flex-start;
  gap: 10px;
  padding: 12px 16px;
  border-bottom: 1px solid #e5e7eb;
  background: var(--color-surface, #ffffff);
  transition: background 0.15s;
  cursor: pointer;
}
.notif-item:last-child { border-bottom: none; }
.notif-item:hover { background: #f9f9fb; }
.notif-item.unread {
  background: var(--color-surface-alt, #f5f5f5);
  border-left: 3px solid var(--color-accent, #4f46e5);
}
.notif-item.unread:hover { background: #ededf7; }

.type-dot { width: 8px; height: 8px; border-radius: 50%; margin-top: 5px; flex-shrink: 0; }
.type-dot.task_assigned { background: var(--color-accent, #4f46e5); }
.type-dot.task_comment { background: var(--color-info, #0ea5e9); }
.type-dot.task_status_changed { background: var(--color-warning, #f59e0b); }
.type-dot.invoice_ready { background: var(--color-success, #10b981); }
.type-dot.reminder { background: var(--color-secondary, #8b5cf6); }

.notif-content { flex: 1; min-width: 0; }
.notif-title {
  font-size: 13px; font-weight: 700; color: var(--color-text, #1a1a2e);
  white-space: nowrap; overflow: hidden; text-overflow: ellipsis;
}
.notif-item:not(.unread) .notif-title { font-weight: 400; color: var(--color-text-muted, #6b7280); }
.notif-body {
  font-size: 12px; color: var(--color-text-muted, #6b7280);
  display: -webkit-box; -webkit-line-clamp: 2; -webkit-box-orient: vertical;
  overflow: hidden; margin-top: 2px;
}
.notif-time {
  font-size: 11px; font-weight: 700; color: var(--color-text-muted, #6b7280);
  display: block; margin-top: 4px;
}

.notif-actions {
  display: flex; align-items: center; gap: 2px;
  flex-shrink: 0; opacity: 0; transition: opacity 0.15s;
}
.notif-item:hover .notif-actions,
.notif-item:focus-within .notif-actions { opacity: 1; }

.action-btn {
  width: 28px; height: 28px; border-radius: 6px; border: none; background: none;
  display: flex; align-items: center; justify-content: center;
  font-size: 15px; cursor: pointer; transition: background 0.15s, color 0.15s;
}
.action-btn.mark-read { color: var(--color-accent, #4f46e5); }
.action-btn.mark-read:hover { background: #f0f0ff; }
.action-btn.dismiss { color: var(--color-text-muted, #6b7280); }
.action-btn.dismiss:hover { background: #fef2f2; color: var(--color-danger, #ef4444); }

.empty-state { padding: 48px 16px; text-align: center; color: var(--color-text-muted, #6b7280); }
.empty-icon { font-size: 28px; display: block; margin-bottom: 8px; color: var(--color-success, #10b981); }
.empty-label { font-size: 14px; }
</style>
