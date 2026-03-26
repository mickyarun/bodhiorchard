<template>
  <div class="bell-wrapper" ref="wrapperRef">
    <button
      class="bell-btn"
      :aria-label="hasUnread ? `Notifications, ${unreadCount} unread` : 'Notifications'"
      aria-haspopup="true"
      :aria-expanded="showPanel"
      @click="toggle"
    >
      <!-- Outline bell (0 unread) -->
      <svg v-if="!hasUnread" class="bell-icon" width="22" height="22" viewBox="0 0 24 24" fill="none" aria-hidden="true">
        <path d="M18 8A6 6 0 0 0 6 8c0 7-3 9-3 9h18s-3-2-3-9" stroke="currentColor" stroke-width="1.75" stroke-linecap="round" stroke-linejoin="round"/>
        <path d="M13.73 21a2 2 0 0 1-3.46 0" stroke="currentColor" stroke-width="1.75" stroke-linecap="round" stroke-linejoin="round"/>
      </svg>
      <!-- Filled bell (>0 unread) -->
      <svg v-else class="bell-icon bell-icon--active" width="22" height="22" viewBox="0 0 24 24" fill="currentColor" aria-hidden="true">
        <path d="M18 8A6 6 0 0 0 6 8c0 7-3 9-3 9h18s-3-2-3-9"/>
        <path d="M13.73 21a2 2 0 0 1-3.46 0" fill="none" stroke="currentColor" stroke-width="1.75" stroke-linecap="round"/>
      </svg>

      <span v-if="hasUnread" class="badge" aria-hidden="true">{{ badgeLabel }}</span>
    </button>

    <Teleport to="body">
      <Transition name="panel">
        <div
          v-if="showPanel"
          ref="panelRef"
          class="notif-panel"
          :style="panelStyle"
          role="dialog"
          aria-label="Notifications"
          aria-modal="true"
        >
          <div v-if="offline" class="offline-banner">
            You're offline — showing cached notifications
          </div>

          <div class="panel-head">
            <h3 class="panel-title">Notifications</h3>
            <button v-if="hasUnread && !offline" class="mark-all-btn" @click="markAllRead">
              Mark all read
            </button>
          </div>

          <div v-if="loading" class="panel-loading">Loading…</div>

          <div v-else class="notif-list" role="list">
            <NotificationItem
              v-for="n in notifications"
              :key="n.id"
              :notification="n"
              @mark-read="markRead"
              @delete="deleteNotification"
            />
            <div v-if="notifications.length === 0" class="empty-state">
              <svg width="32" height="32" viewBox="0 0 24 24" fill="none" aria-hidden="true">
                <path d="M18 8A6 6 0 0 0 6 8c0 7-3 9-3 9h18s-3-2-3-9" stroke="#bbb" stroke-width="1.5" stroke-linecap="round"/>
                <path d="M13.73 21a2 2 0 0 1-3.46 0" stroke="#bbb" stroke-width="1.5" stroke-linecap="round"/>
              </svg>
              <p>You're all caught up</p>
            </div>
          </div>

          <div class="panel-footer">
            <a href="/notifications">View all notifications →</a>
          </div>
        </div>
      </Transition>

      <Transition name="toast">
        <div v-if="toastError" class="toast" role="alert" aria-live="assertive">
          {{ toastError }}
        </div>
      </Transition>
    </Teleport>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, watch, nextTick, onMounted, onUnmounted } from 'vue'
import NotificationItem from './NotificationItem.vue'
import { useNotifications } from '@/composables/useNotifications'

const {
  notifications, loading, offline, toastError,
  unreadCount, badgeLabel, hasUnread,
  fetchNotifications, markRead, markAllRead, deleteNotification,
} = useNotifications()

const wrapperRef = ref<HTMLElement | null>(null)
const panelRef = ref<HTMLElement | null>(null)
const showPanel = ref(false)
const panelPos = ref({ top: 0, right: 0, width: 360 })

function computePosition() {
  if (!wrapperRef.value) return
  const rect = wrapperRef.value.getBoundingClientRect()
  const width = Math.min(360, window.innerWidth - 16)
  // Anchor right edge of panel to right edge of bell, but clamp so panel never goes off left
  const desiredRight = window.innerWidth - rect.right
  const clampedRight = Math.max(desiredRight, 8)
  panelPos.value = { top: rect.bottom + 8, right: clampedRight, width }
}

const panelStyle = computed(() => ({
  position: 'fixed' as const,
  top: `${panelPos.value.top}px`,
  right: `${panelPos.value.right}px`,
  width: `${panelPos.value.width}px`,
}))

function toggle() {
  showPanel.value = !showPanel.value
}

function close() {
  showPanel.value = false
}

watch(showPanel, (open) => {
  if (open) {
    computePosition()
    fetchNotifications()
  }
})

function handleOutsideClick(e: MouseEvent) {
  const target = e.target as Element
  if (!wrapperRef.value?.contains(target) && !panelRef.value?.contains(target)) {
    close()
  }
}

function handleEscape(e: KeyboardEvent) {
  if (e.key === 'Escape') close()
}

onMounted(() => {
  document.addEventListener('click', handleOutsideClick)
  window.addEventListener('keydown', handleEscape)
  window.addEventListener('resize', computePosition)
})

onUnmounted(() => {
  document.removeEventListener('click', handleOutsideClick)
  window.removeEventListener('keydown', handleEscape)
  window.removeEventListener('resize', computePosition)
})
</script>

<style scoped>
.bell-wrapper {
  display: inline-flex;
  align-items: center;
}

.bell-btn {
  position: relative;
  background: transparent;
  border: none;
  cursor: pointer;
  padding: 8px;
  border-radius: 8px;
  display: flex;
  align-items: center;
  justify-content: center;
  color: #e0e0e0;
  transition: background 0.15s, color 0.15s;
  min-width: 44px;
  min-height: 44px;
}
.bell-btn:hover { background: rgba(255,255,255,0.1); }
.bell-btn:focus-visible { outline: 2px solid #fff; outline-offset: 2px; }

.bell-icon--active { color: #fff; }

.badge {
  position: absolute;
  top: 4px;
  right: 4px;
  background: var(--color-danger, #c62828);
  color: #fff;
  font-size: 10px;
  font-weight: 700;
  line-height: 1;
  padding: 2px 4px;
  border-radius: 8px;
  min-width: 16px;
  text-align: center;
  pointer-events: none;
}
</style>

<!-- Panel styles are NOT scoped — the panel is teleported to <body> outside this component's DOM subtree -->
<style>
.notif-panel {
  max-height: 480px;
  background: #fff;
  border-radius: 8px;
  box-shadow: 0 8px 28px rgba(0,0,0,0.18);
  z-index: 9999;
  display: flex;
  flex-direction: column;
  overflow: hidden;
}

.offline-banner {
  background: #f57c00;
  color: #fff;
  font-size: 12px;
  font-weight: 500;
  padding: 6px 16px;
  text-align: center;
}

.panel-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 14px 16px 10px;
  border-bottom: 1px solid #f0f0f0;
  flex-shrink: 0;
}
.panel-title {
  margin: 0;
  font-size: 15px;
  font-weight: 700;
  color: #1a1a2e;
}
.mark-all-btn {
  background: none;
  border: none;
  font-size: 12px;
  font-weight: 500;
  color: #5c6bc0;
  cursor: pointer;
  padding: 4px 8px;
  border-radius: 4px;
  transition: background 0.12s;
}
.mark-all-btn:hover { background: #e8eaf6; }

.panel-loading {
  padding: 24px 16px;
  text-align: center;
  font-size: 13px;
  color: #757575;
}

.notif-list {
  flex: 1;
  overflow-y: auto;
  overscroll-behavior: contain;
}

.empty-state {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 8px;
  padding: 40px 16px;
  color: #757575;
  font-size: 13px;
}
.empty-state p { margin: 0; }

.panel-footer {
  padding: 10px 16px;
  border-top: 1px solid #f0f0f0;
  flex-shrink: 0;
}
.panel-footer a {
  font-size: 12px;
  color: #5c6bc0;
  text-decoration: none;
  font-weight: 500;
}
.panel-footer a:hover { text-decoration: underline; }

.toast {
  position: fixed;
  bottom: 24px;
  right: 24px;
  background: #c62828;
  color: #fff;
  font-size: 13px;
  padding: 10px 16px;
  border-radius: 6px;
  box-shadow: 0 4px 12px rgba(0,0,0,0.2);
  white-space: nowrap;
  z-index: 10000;
}

/* Panel transition */
.panel-enter-active, .panel-leave-active {
  transition: opacity 0.15s ease, transform 0.15s ease;
}
.panel-enter-from, .panel-leave-to {
  opacity: 0;
  transform: translateY(-6px);
}

/* Toast transition */
.toast-enter-active, .toast-leave-active { transition: opacity 0.2s ease; }
.toast-enter-from, .toast-leave-to { opacity: 0; }
</style>
