<!--
 * Copyright 2025-2026 Arun Rajkumar
 *
 * Licensed under the Apache License, Version 2.0 (the "License");
 * you may not use this file except in compliance with the License.
 * You may obtain a copy of the License at
 *
 *     http://www.apache.org/licenses/LICENSE-2.0
 *
 * Unless required by applicable law or agreed to in writing, software
 * distributed under the License is distributed on an "AS IS" BASIS,
 * WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
 * See the License for the specific language governing permissions and
 * limitations under the License.
 -->

<script setup lang="ts">
import { computed } from 'vue'
import { BUD_STATUS_COLORS, BUD_STATUS_LABELS } from '@/types'
import type { BUDDocument, BUDStatus, TimelineEvent } from '@/types'
import { formatDateTime } from '@/utils/date'

const props = defineProps<{
  bud: BUDDocument
  timelineEvents: TimelineEvent[]
}>()

const isClosureEvent = (e: TimelineEvent): boolean =>
  e.event_type === 'status_change'
  && (e.detail?.to === 'closed' || e.detail?.to === 'discarded')

const closureEvents = computed(() => props.timelineEvents.filter(isClosureEvent))

const closedEvent = computed(() =>
  closureEvents.value.length > 0
    ? closureEvents.value[closureEvents.value.length - 1]
    : null,
)

const closedReason = computed(() => (closedEvent.value?.detail?.reason as string) || null)
const closedFrom = computed(() => (closedEvent.value?.detail?.from as string) || null)

const isDiscarded = computed(() => props.bud.status === 'discarded')
</script>

<template>
  <div class="pa-4">
    <v-alert
      :type="isDiscarded ? 'error' : 'info'"
      variant="tonal"
      density="compact"
      class="mb-5"
    >
      <div class="d-flex align-center ga-2">
        <v-icon :icon="isDiscarded ? 'mdi-delete-outline' : 'mdi-check-circle-outline'" />
        <div class="flex-grow-1">
          <div class="font-weight-medium">
            {{ isDiscarded ? 'This BUD was discarded' : 'This BUD is closed' }}
          </div>
          <div v-if="closedEvent" class="text-caption text-medium-emphasis">
            {{ closedEvent.actor_name || 'System' }} &middot; {{ formatDateTime(closedEvent.created_at) }}
          </div>
        </div>
      </div>
    </v-alert>

    <!-- Release / closure date -->
    <div v-if="closedEvent" class="mb-5">
      <div class="text-overline text-medium-emphasis mb-2">
        {{ isDiscarded ? 'Discarded on' : 'Completed on' }}
      </div>
      <div class="d-flex align-center ga-2">
        <v-icon icon="mdi-calendar-check" size="18" color="success" />
        <span class="text-body-1 font-weight-medium">
          {{ formatDateTime(closedEvent.created_at) }}
        </span>
      </div>
    </div>

    <!-- Closure reason (from status_override or status_change detail) -->
    <div v-if="closedReason" class="mb-5">
      <div class="text-overline text-medium-emphasis mb-2">Reason</div>
      <v-card variant="outlined" class="pa-3">
        <div class="text-body-2">{{ closedReason }}</div>
      </v-card>
    </div>

    <!-- Previous status before closure -->
    <div v-if="closedFrom" class="mb-5">
      <div class="text-overline text-medium-emphasis mb-2">Closed from</div>
      <v-chip
        variant="tonal"
        :color="BUD_STATUS_COLORS[closedFrom as BUDStatus] || 'grey'"
        size="small"
      >
        {{ BUD_STATUS_LABELS[closedFrom as BUDStatus] || closedFrom }}
      </v-chip>
    </div>

    <!-- Closure timeline events -->
    <div v-if="closureEvents.length" class="mb-5">
      <div class="text-overline text-medium-emphasis mb-2">Timeline</div>
      <div class="d-flex flex-column ga-2">
        <div
          v-for="event in closureEvents"
          :key="event.id"
          class="d-flex align-center ga-2 pa-2 rounded closure-row"
        >
          <v-icon
            :icon="event.event_type === 'status_change' ? 'mdi-swap-horizontal' : 'mdi-information-outline'"
            size="18"
            color="primary"
          />
          <div class="flex-grow-1">
            <span class="text-body-2">
              {{ event.event_type === 'status_change'
                ? `Status changed: ${event.detail?.from || '?'} → ${event.detail?.to || '?'}`
                : event.event_type.replace(/_/g, ' ')
              }}
            </span>
            <div class="text-caption text-medium-emphasis">
              {{ event.actor_name || 'System' }} &middot; {{ formatDateTime(event.created_at) }}
            </div>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.closure-row {
  border: 1px solid rgba(var(--v-theme-on-surface), 0.08);
}
</style>
