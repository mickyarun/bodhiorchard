<template>
  <div ref="containerRef" class="notification-bell">
    <button
      ref="bellBtnRef"
      class="bell-btn"
      :aria-label="`Notifications, ${store.badgeLabel} unread`"
      aria-haspopup="true"
      :aria-expanded="panelOpen"
      @click="togglePanel"
    >
      <svg
        class="bell-icon"
        :class="{ filled: store.hasUnread }"
        width="20"
        height="20"
        viewBox="0 0 24 24"
        fill="none"
        stroke="currentColor"
        stroke-width="1.75"
        stroke-linecap="round"
        stroke-linejoin="round"
      >
        <path d="M18 8A6 6 0 0 0 6 8c0 7-3 9-3 9h18s-3-2-3-9" />
        <path d="M13.73 21a2 2 0 0 1-3.46 0" />
      </svg>
      <span v-if="store.hasUnread" class="badge" aria-hidden="true">
        {{ store.badgeLabel }}
      </span>
    </button>

    <NotificationPanel v-if="panelOpen" @close="closePanel" />
  </div>
</template>

<script setup lang="ts">
import { ref } from 'vue'
import { useNotificationStore } from '@/stores/notifications'
import { useClickOutside } from '@/composables/useClickOutside'
import NotificationPanel from './NotificationPanel.vue'

const store = useNotificationStore()
const panelOpen = ref(false)
const containerRef = ref<HTMLElement | null>(null)
const bellBtnRef = ref<HTMLButtonElement | null>(null)

useClickOutside(containerRef, () => {
  if (panelOpen.value) closePanel()
})

function togglePanel() {
  panelOpen.value = !panelOpen.value
  if (panelOpen.value) {
    store.fetchNotifications()
  }
}

function closePanel() {
  panelOpen.value = false
  bellBtnRef.value?.focus()
}
</script>

<style scoped>
.notification-bell {
  position: relative;
  margin-left: auto;
}
.bell-btn {
  position: relative;
  display: flex;
  align-items: center;
  justify-content: center;
  width: 36px;
  height: 36px;
  border: none;
  border-radius: 8px;
  background: transparent;
  color: #e0e0e0;
  cursor: pointer;
  transition: background 0.15s;
}
.bell-btn:hover {
  background: rgba(255, 255, 255, 0.1);
}
.bell-btn:focus-visible {
  outline: 2px solid var(--color-accent, #4f46e5);
  outline-offset: 2px;
}
.bell-icon.filled {
  fill: currentColor;
  fill-opacity: 0.15;
}
.badge {
  position: absolute;
  top: 2px;
  right: 2px;
  min-width: 18px;
  height: 18px;
  padding: 0 5px;
  border-radius: 9px;
  background: var(--color-accent, #4f46e5);
  color: #fff;
  font-size: 11px;
  font-weight: 700;
  line-height: 18px;
  text-align: center;
  pointer-events: none;
}
</style>
