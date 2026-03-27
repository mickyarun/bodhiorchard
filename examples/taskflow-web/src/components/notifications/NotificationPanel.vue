<template>
  <div
    ref="panelRef"
    class="notification-panel"
    role="region"
    aria-label="Notifications"
    @keydown.escape="$emit('close')"
    tabindex="-1"
  >
    <div class="panel-header">
      <h3>Notifications</h3>
      <button
        v-if="store.hasUnread"
        class="mark-all-btn"
        @click="store.markAllRead()"
      >
        Mark all read
      </button>
    </div>

    <div v-if="store.error" class="panel-error">
      {{ store.error }}
    </div>

    <div class="panel-body">
      <div v-if="store.loading" class="panel-loading">
        <div v-for="i in 3" :key="i" class="skeleton-item">
          <div class="skeleton-dot"></div>
          <div class="skeleton-lines">
            <div class="skeleton-line long"></div>
            <div class="skeleton-line short"></div>
          </div>
        </div>
      </div>

      <template v-else-if="store.notifications.length > 0">
        <NotificationItem
          v-for="n in store.notifications"
          :key="n.id"
          :notification="n"
        />
      </template>

      <div v-else class="panel-empty">
        <span class="empty-icon">&#10003;</span>
        <p>You're all caught up</p>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { useNotificationStore } from '@/stores/notifications'
import NotificationItem from './NotificationItem.vue'

defineEmits<{ close: [] }>()

const store = useNotificationStore()
const panelRef = ref<HTMLElement | null>(null)

onMounted(() => {
  panelRef.value?.focus()
})
</script>

<style scoped>
.notification-panel {
  position: fixed;
  top: 52px;
  right: 16px;
  width: 380px;
  max-height: 480px;
  background: var(--color-surface, #ffffff);
  border-radius: var(--radius-panel, 12px);
  box-shadow: var(--shadow-panel, 0 8px 32px rgba(0, 0, 0, 0.12));
  display: flex;
  flex-direction: column;
  z-index: 1000;
  outline: none;
  overflow: hidden;
}
.panel-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 16px;
  border-bottom: 1px solid #eee;
}
.panel-header h3 {
  margin: 0;
  font-size: 15px;
  font-weight: 700;
  color: var(--color-text, #1a1a2e);
}
.mark-all-btn {
  border: none;
  background: none;
  color: var(--color-accent, #4f46e5);
  font-size: 13px;
  font-weight: 500;
  cursor: pointer;
  padding: 4px 8px;
  border-radius: 6px;
}
.mark-all-btn:hover {
  background: #f0f0ff;
}
.mark-all-btn:focus-visible {
  outline: 2px solid var(--color-accent, #4f46e5);
  outline-offset: 1px;
}
.panel-error {
  padding: 8px 16px;
  background: #fef2f2;
  color: var(--color-danger, #ef4444);
  font-size: 12px;
}
.panel-body {
  overflow-y: auto;
  flex: 1;
}
.panel-empty {
  padding: 48px 16px;
  text-align: center;
  color: var(--color-text-muted, #6b7280);
}
.empty-icon {
  font-size: 28px;
  display: block;
  margin-bottom: 8px;
  color: #10b981;
}
.panel-empty p {
  margin: 0;
  font-size: 14px;
}

/* Loading skeleton */
.panel-loading {
  padding: 8px 0;
}
.skeleton-item {
  display: flex;
  align-items: flex-start;
  gap: 10px;
  padding: 12px 16px;
}
.skeleton-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: #e5e7eb;
  margin-top: 6px;
}
.skeleton-lines {
  flex: 1;
}
.skeleton-line {
  height: 12px;
  border-radius: 4px;
  background: #e5e7eb;
  animation: pulse 1.5s ease-in-out infinite;
}
.skeleton-line.long { width: 80%; margin-bottom: 8px; }
.skeleton-line.short { width: 50%; }
@keyframes pulse {
  0%, 100% { opacity: 1; }
  50% { opacity: 0.4; }
}

@media (max-width: 440px) {
  .notification-panel {
    right: 8px;
    left: 8px;
    width: auto;
  }
}
</style>
