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
import AppCallout from '@/components/common/AppCallout.vue'

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

function statusLabel(status: unknown): string {
  const s = String(status ?? '')
  return BUD_STATUS_LABELS[s as BUDStatus] || s || 'unknown'
}
</script>

<template>
  <div class="closed-tab">
    <AppCallout
      :variant="isDiscarded ? 'error' : 'success'"
      :icon="isDiscarded ? 'mdi-delete-outline' : 'mdi-check-circle-outline'"
      :title="isDiscarded ? 'This BUD was discarded' : 'This BUD is closed'"
    >
      <template v-if="closedEvent">{{ closedEvent.actor_name || 'System' }} · {{ formatDateTime(closedEvent.created_at) }}</template>
    </AppCallout>

    <dl class="closed-tab__facts">
      <template v-if="closedEvent">
        <dt>{{ isDiscarded ? 'Discarded on' : 'Completed on' }}</dt>
        <dd>{{ formatDateTime(closedEvent.created_at) }}</dd>
      </template>
      <!-- From the status_override or status_change detail. -->
      <template v-if="closedReason">
        <dt>Reason</dt>
        <dd class="closed-tab__reason">{{ closedReason }}</dd>
      </template>
      <template v-if="closedFrom">
        <dt>{{ isDiscarded ? 'Discarded from' : 'Closed from' }}</dt>
        <dd><v-chip variant="tonal" :color="BUD_STATUS_COLORS[closedFrom as BUDStatus] || 'muted'" size="small">{{ statusLabel(closedFrom) }}</v-chip></dd>
      </template>
    </dl>

    <section v-if="closureEvents.length" aria-labelledby="closed-tab-timeline">
      <h3 id="closed-tab-timeline" class="closed-tab__heading">Timeline</h3>
      <ul class="closed-tab__events">
        <li v-for="event in closureEvents" :key="event.id" class="closed-tab__event">
          <v-icon
            :icon="event.event_type === 'status_change' ? 'mdi-swap-horizontal' : 'mdi-information-outline'"
            size="18"
            color="primary"
          />
          <div>
            <div>
              {{ event.event_type === 'status_change'
                ? `Moved from ${statusLabel(event.detail?.from)} to ${statusLabel(event.detail?.to)}`
                : event.event_type.replace(/_/g, ' ') }}
            </div>
            <div class="closed-tab__meta">{{ event.actor_name || 'System' }} · {{ formatDateTime(event.created_at) }}</div>
          </div>
        </li>
      </ul>
    </section>
  </div>
</template>

<style scoped>
.closed-tab {
  display: flex;
  flex-direction: column;
  gap: 20px;
  padding: 20px;
}
.closed-tab__facts {
  margin: 0;
  display: grid;
  grid-template-columns: 140px minmax(0, 1fr);
  gap: 12px;
  font-size: 14px;
}
.closed-tab__facts dt,
.closed-tab__meta {
  color: rgb(var(--v-theme-on-surface-variant));
}
.closed-tab__facts dd {
  margin: 0;
}
.closed-tab__reason {
  white-space: pre-wrap;
}
.closed-tab__heading {
  margin: 0 0 8px;
  font-size: 14px;
  font-weight: 600;
}
.closed-tab__events {
  list-style: none;
  margin: 0;
  padding: 0;
  display: flex;
  flex-direction: column;
  gap: 8px;
}
.closed-tab__event {
  display: flex;
  align-items: flex-start;
  gap: 8px;
  padding: 8px 10px;
  font-size: 14px;
  border: 1px solid rgb(var(--v-theme-rule));
  border-radius: var(--radius-input);
}
.closed-tab__meta {
  font-size: 12px;
}
@media (max-width: 600px) {
  .closed-tab__facts {
    grid-template-columns: minmax(0, 1fr);
    gap: 4px;
  }
  .closed-tab__facts dd {
    margin-bottom: 8px;
  }
}
</style>
