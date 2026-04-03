<template>
  <v-card color="surface" class="pa-4">
    <div class="text-subtitle-1 font-weight-bold mb-3">
      <v-icon icon="mdi-history" size="18" class="mr-1" />
      Recent XP Activity
    </div>

    <v-progress-linear v-if="loading" indeterminate color="primary" class="mb-2" />

    <v-list v-if="events.length > 0" density="compact" class="bg-transparent">
      <v-list-item
        v-for="event in events"
        :key="event.id"
        class="px-0"
      >
        <template #prepend>
          <v-icon
            :icon="getSourceIcon(event.source)"
            size="18"
            color="primary"
            class="mr-2"
          />
        </template>

        <v-list-item-title class="text-body-2">
          {{ getSourceLabel(event.source) }}
          <v-chip
            v-if="event.multiplier > 1"
            size="x-small"
            color="warning"
            variant="tonal"
            class="ml-1"
          >
            {{ event.multiplier }}x
          </v-chip>
        </v-list-item-title>

        <v-list-item-subtitle class="text-caption">
          {{ timeAgo(event.created_at) }}
        </v-list-item-subtitle>

        <template #append>
          <span class="text-body-2 font-weight-bold" style="color: rgb(var(--v-theme-primary));">
            +{{ event.xp_amount }}
          </span>
        </template>
      </v-list-item>
    </v-list>

    <div v-else-if="!loading" class="text-caption text-medium-emphasis text-center py-4">
      No XP activity yet. Start coding!
    </div>
  </v-card>
</template>

<script setup lang="ts">
import { onMounted, ref } from 'vue'
import type { XPEvent } from '@/types'
import { useXPStore } from '@/stores/xp'
import { getSourceLabel, getSourceIcon } from '@/composables/useXPSocket'

const xpStore = useXPStore()
const loading = ref(true)
const events = ref<XPEvent[]>([])

function timeAgo(isoDate: string): string {
  const diff = Date.now() - new Date(isoDate).getTime()
  const mins = Math.floor(diff / 60000)
  if (mins < 1) return 'just now'
  if (mins < 60) return `${mins}m ago`
  const hours = Math.floor(mins / 60)
  if (hours < 24) return `${hours}h ago`
  const days = Math.floor(hours / 24)
  return `${days}d ago`
}

onMounted(async () => {
  await xpStore.fetchHistory()
  events.value = xpStore.history
  loading.value = false
})
</script>
