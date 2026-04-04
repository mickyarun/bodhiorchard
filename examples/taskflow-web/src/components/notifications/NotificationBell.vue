<template>
  <div class="bell-wrap">
    <button
      class="bell-btn"
      @click="togglePanel"
      :aria-label="unreadCount > 0
        ? unreadCount + ' unread notifications, open panel'
        : 'Notifications, open panel'"
      :aria-expanded="showPanel"
      aria-haspopup="dialog"
    >
      <!-- Outline bell when no unread -->
      <svg v-if="unreadCount === 0" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
        <path d="M18 8A6 6 0 0 0 6 8c0 7-3 9-3 9h18s-3-2-3-9"/>
        <path d="M13.73 21a2 2 0 0 1-3.46 0"/>
      </svg>
      <!-- Filled bell when unread exist -->
      <svg v-else viewBox="0 0 24 24" fill="currentColor" aria-hidden="true">
        <path d="M12 22a2 2 0 0 0 2-2H10a2 2 0 0 0 2 2zm6-6V11a6 6 0 0 0-5-5.91V4a1 1 0 0 0-2 0v1.09A6 6 0 0 0 6 11v5l-2 2v1h16v-1l-2-2z"/>
      </svg>
      <span v-if="unreadCount > 0" class="badge" aria-hidden="true">{{ badgeLabel }}</span>
    </button>

    <!-- Backdrop — click outside to close -->
    <div
      v-if="showPanel"
      class="overlay-backdrop"
      @click="closePanel"
      aria-hidden="true"
    ></div>

    <NotificationPanel v-if="showPanel" ref="panelRef" @close="closePanel" />

    <!-- Error Snackbar -->
    <div v-if="store.error" class="snackbar" role="alert" aria-live="assertive">
      {{ store.error }}
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, watch, onMounted, onUnmounted } from 'vue'
import { useNotificationStore } from '@/stores/notifications'
import { useNotificationSocket } from '@/composables/useNotificationSocket'
import NotificationPanel from './NotificationPanel.vue'

const store = useNotificationStore()
const panelRef = ref<InstanceType<typeof NotificationPanel> | null>(null)
const showPanel = ref(false)

const unreadCount = computed(() => store.unreadCount)
const badgeLabel = computed(() =>
  unreadCount.value > 99 ? '99+' : String(unreadCount.value),
)

function togglePanel() {
  showPanel.value = !showPanel.value
  if (!showPanel.value) panelRef.value?.resetConfirm()
}

function closePanel() {
  showPanel.value = false
}

function onKeyDown(e: KeyboardEvent) {
  if (e.key === 'Escape' && showPanel.value) closePanel()
}

// Auto-dismiss error snackbar after 3 seconds
let errorTimer: ReturnType<typeof setTimeout> | undefined
watch(() => store.error, (msg) => {
  if (errorTimer) clearTimeout(errorTimer)
  if (msg) {
    errorTimer = setTimeout(() => { store.error = '' }, 3000)
  }
})

onMounted(() => {
  store.fetchAll()
  document.addEventListener('keydown', onKeyDown)
})

onUnmounted(() => {
  document.removeEventListener('keydown', onKeyDown)
  if (errorTimer) clearTimeout(errorTimer)
})

// Wire real-time updates (userId would come from auth context)
useNotificationSocket('current-user')
</script>

<style scoped>
.bell-wrap { position: relative; }

.bell-btn {
  position: relative;
  width: 40px;
  height: 40px;
  border-radius: 8px;
  border: none;
  background: none;
  display: flex;
  align-items: center;
  justify-content: center;
  color: #e0e0e0;
  cursor: pointer;
  transition: background 0.15s;
}
.bell-btn:hover { background: rgba(255, 255, 255, 0.1); }
.bell-btn:focus-visible {
  outline: 2px solid var(--color-accent, #4f46e5);
  outline-offset: 2px;
}
.bell-btn svg { width: 20px; height: 20px; }

.badge {
  position: absolute;
  top: 4px;
  right: 4px;
  background: var(--color-danger, #ef4444);
  color: #fff;
  font-size: 10px;
  font-weight: 700;
  min-width: 16px;
  height: 16px;
  padding: 0 4px;
  border-radius: 8px;
  display: flex;
  align-items: center;
  justify-content: center;
  line-height: 1;
  pointer-events: none;
}

.overlay-backdrop {
  position: fixed;
  inset: 0;
  z-index: 999;
}

.snackbar {
  position: fixed;
  bottom: 24px;
  left: 50%;
  transform: translateX(-50%);
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 10px 18px;
  border-radius: 8px;
  font-size: 13px;
  font-weight: 500;
  z-index: 2000;
  box-shadow: 0 4px 16px rgba(0, 0, 0, 0.15);
  background: #fef2f2;
  color: var(--color-danger, #ef4444);
  border: 1px solid #fecaca;
}
</style>
