<template>
  <v-menu
    v-model="menuOpen"
    location="top start"
    :close-on-content-click="false"
    max-width="380"
    min-width="340"
  >
    <template #activator="{ props: menuProps }">
      <v-btn
        v-bind="menuProps"
        icon
        variant="text"
        size="default"
        density="comfortable"
        class="notification-bell-btn"
      >
        <v-badge
          :content="store.unreadCount"
          :model-value="store.unreadCount > 0"
          color="error"
          dot-margin="-2px"
          offset-x="2"
          offset-y="2"
        >
          <v-icon icon="mdi-bell-outline" size="22" />
        </v-badge>
      </v-btn>
    </template>

    <v-card class="notification-panel" elevation="8">
      <!-- Header -->
      <v-card-title class="d-flex align-center justify-space-between pa-3 pb-1">
        <span class="text-body-1 font-weight-medium">Notifications</span>
        <v-btn
          v-if="store.unreadCount > 0"
          variant="text"
          size="small"
          density="compact"
          color="primary"
          @click="store.markAllRead()"
        >
          Mark all read
        </v-btn>
      </v-card-title>

      <v-divider />

      <!-- Notification list -->
      <v-list
        v-if="store.items.length > 0"
        density="compact"
        class="notification-list pa-0"
      >
        <template v-for="notif in store.items" :key="notif.id">
          <v-list-item
            class="notification-item px-3 py-2"
            :class="{ 'notification-unread': !notif.isRead }"
            @click="handleClick(notif)"
          >
            <template #prepend>
              <v-icon
                :icon="notifIcon(notif.type)"
                :color="notifColor(notif.type)"
                size="20"
                class="mr-3"
              />
            </template>

            <v-list-item-title class="text-body-2 font-weight-medium">
              {{ notif.title }}
            </v-list-item-title>
            <v-list-item-subtitle v-if="notif.message" class="text-caption mt-1">
              {{ notif.message }}
            </v-list-item-subtitle>
            <v-list-item-subtitle class="text-caption text-medium-emphasis mt-1">
              {{ relativeTime(notif.createdAt) }}
            </v-list-item-subtitle>

            <template #append>
              <div class="d-flex align-center ga-1">
                <v-btn
                  v-if="notif.deepLink"
                  icon
                  variant="text"
                  size="x-small"
                  density="compact"
                  @click.stop="navigateTo(notif)"
                >
                  <v-icon icon="mdi-arrow-right" size="16" />
                </v-btn>
                <v-btn
                  icon
                  variant="text"
                  size="x-small"
                  density="compact"
                  @click.stop="store.dismiss(notif.id)"
                >
                  <v-icon icon="mdi-close" size="14" />
                </v-btn>
              </div>
            </template>
          </v-list-item>
          <v-divider />
        </template>
      </v-list>

      <!-- Empty state -->
      <div v-else class="text-center pa-6 text-medium-emphasis">
        <v-icon icon="mdi-bell-check-outline" size="32" class="mb-2 d-block mx-auto" />
        <div class="text-body-2">No notifications</div>
      </div>

      <!-- Footer -->
      <template v-if="store.items.length > 0">
        <v-divider />
        <v-card-actions class="justify-center pa-2">
          <v-btn
            variant="text"
            size="small"
            density="compact"
            color="error"
            @click="handleClearAll"
          >
            Clear all
          </v-btn>
        </v-card-actions>
      </template>
    </v-card>
  </v-menu>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { useNotificationStore } from '@/stores/notifications'
import { useNotificationSocket } from '@/composables/useNotificationSocket'
import type { AppNotification } from '@/types'

const props = defineProps<{ userId: string }>()

const store = useNotificationStore()
const router = useRouter()
const menuOpen = ref(false)

useNotificationSocket(props.userId)

onMounted(() => {
  store.fetchAll()
})

function handleClick(notif: AppNotification): void {
  if (!notif.isRead) {
    store.markRead(notif.id)
  }
  if (notif.deepLink) {
    navigateTo(notif)
  }
}

function navigateTo(notif: AppNotification): void {
  if (!notif.isRead) {
    store.markRead(notif.id)
  }
  menuOpen.value = false
  if (notif.deepLink) {
    router.push(notif.deepLink)
  }
}

function handleClearAll(): void {
  store.dismissAll()
  menuOpen.value = false
}

function notifIcon(type: string): string {
  switch (type) {
    case 'job_failed': return 'mdi-alert-circle'
    case 'approval_requested': return 'mdi-bell-ring-outline'
    case 'approval_granted': return 'mdi-check-decagram'
    case 'approval_rejected': return 'mdi-close-circle-outline'
    case 'developer_assigned': return 'mdi-account-check'
    case 'reassignment_done': return 'mdi-swap-horizontal'
    default: return 'mdi-check-circle'
  }
}

function notifColor(type: string): string {
  switch (type) {
    case 'job_failed':
    case 'approval_rejected': return 'error'
    case 'approval_requested': return 'warning'
    case 'developer_assigned':
    case 'reassignment_done': return 'info'
    default: return 'success'
  }
}

function relativeTime(isoString: string): string {
  const now = Date.now()
  const then = new Date(isoString).getTime()
  const diffSec = Math.floor((now - then) / 1000)

  if (diffSec < 60) return 'just now'
  const diffMin = Math.floor(diffSec / 60)
  if (diffMin < 60) return `${diffMin}m ago`
  const diffHr = Math.floor(diffMin / 60)
  if (diffHr < 24) return `${diffHr}h ago`
  const diffDay = Math.floor(diffHr / 24)
  return `${diffDay}d ago`
}
</script>

<style scoped>
.notification-bell-btn {
  overflow: visible !important;
}

.notification-panel {
  max-height: 480px;
  display: flex;
  flex-direction: column;
}

.notification-list {
  overflow-y: auto;
  max-height: 360px;
}

.notification-unread {
  background: rgba(var(--v-theme-primary), 0.04);
}

.notification-item:hover {
  background: rgba(var(--v-theme-on-surface), 0.04);
  cursor: pointer;
}
</style>
