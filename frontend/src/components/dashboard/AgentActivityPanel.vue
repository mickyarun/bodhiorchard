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

<!-- Agent activity: the most recent agent runs, newest first, with a live
     count of agents working right now. -->
<template>
  <AppPanel title="Agent activity" :note="workingLabel">
    <ol v-if="recent.length" class="activity">
      <li v-for="(event, i) in recent" :key="`${event.task_id ?? event.timestamp}-${i}`" class="activity__row">
        <span class="activity__icon" :class="`activity__icon--${tone(event.status)}`" aria-hidden="true">
          <v-icon :icon="ICONS[tone(event.status)]" size="16" />
        </span>
        <span class="activity__text">
          <span class="activity__line"><strong>{{ event.agent_name }}</strong> {{ event.action }}</span>
          <span class="activity__meta">
            {{ event.timestamp ? timeAgo(event.timestamp) : 'Now' }}
            <template v-if="event.bud_number"> · {{ budRef(event.bud_number) }} {{ event.bud_title }}</template>
          </span>
        </span>
      </li>
    </ol>
    <p v-else class="activity__empty">No agent has run yet. Agents start when a BUD moves to a stage they own.</p>
  </AppPanel>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import AppPanel from '@/components/common/AppPanel.vue'
import { budRef } from '@/types'
import type { AgentActivityItem } from '@/types/dashboard'
import { timeAgo } from '@/utils/dev-activity-helpers'

type Tone = 'working' | 'done' | 'failed'

const ICONS: Record<Tone, string> = {
  working: 'mdi-robot-outline',
  done: 'mdi-check',
  failed: 'mdi-alert-circle-outline',
}
const LIMIT = 5

const props = defineProps<{
  activity: AgentActivityItem[]
  /** When the activity was loaded; the running count is as of then. */
  asOf: Date | null
}>()

function tone(status: string): Tone {
  if (status === 'failed') return 'failed'
  if (status === 'running' || status === 'pending') return 'working'
  return 'done'
}

const recent = computed(() =>
  [...props.activity].sort((a, b) => b.timestamp.localeCompare(a.timestamp)).slice(0, LIMIT),
)
const working = computed(() => props.activity.filter(a => tone(a.status) === 'working').length)
const workingLabel = computed(() => {
  const count = working.value === 1 ? '1 agent working' : `${working.value} agents working`
  const label = working.value ? count : 'None working'
  if (!props.asOf) return label
  const time = props.asOf.toLocaleTimeString(undefined, { hour: 'numeric', minute: '2-digit' })
  return `${label} · as of ${time}`
})
</script>

<style scoped>
.activity {
  list-style: none;
  margin: 0;
  padding: 0;
}
.activity__row {
  display: flex;
  gap: 12px;
  padding: 8px 0;
}
.activity__icon {
  width: 30px;
  height: 30px;
  flex-shrink: 0;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  border-radius: 8px;
  background: rgb(var(--v-theme-surface-variant));
  color: rgb(var(--v-theme-on-surface-variant));
}
.activity__icon--working {
  background: rgba(var(--v-theme-primary), 0.14);
  color: var(--color-accent-text);
}
.activity__icon--failed {
  background: rgba(var(--v-theme-error), 0.14);
  color: rgb(var(--v-theme-error));
}
.activity__text {
  display: flex;
  flex-direction: column;
  gap: 2px;
  min-width: 0;
}
.activity__line {
  font-size: var(--text-sm);
  line-height: 20px;
  overflow-wrap: anywhere;
}
.activity__meta,
.activity__empty {
  font-size: 12px;
  color: rgb(var(--v-theme-on-surface-variant));
}
.activity__empty {
  margin: 0;
  font-size: var(--text-sm);
}
</style>
