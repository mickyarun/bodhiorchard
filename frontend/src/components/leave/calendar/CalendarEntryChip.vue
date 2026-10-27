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

<!-- Someone out on the team calendar. Leave is a tinted chip, WFH an
     outline with a house; a request still waiting for approval has a dashed
     warning border. Colour is status only: the leave type never shows here
     (the API withholds it from coworkers anyway). -->
<template>
  <span
    class="entry"
    :class="{
      'entry--wfh': entry.kind === 'wfh',
      'entry--pending': entry.status === 'pending',
    }"
    :title="title"
  >
    <v-icon v-if="entry.kind === 'wfh'" icon="mdi-home-outline" size="12" aria-hidden="true" />
    <span class="entry__name">{{ entry.user.name }}</span>
    <span v-if="entry.half_day !== 'none'" class="entry__half">· ½</span>
  </span>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import type { CalendarEntry } from '@/types/leave'
import { HALF_DAY_LABELS, KIND_LABELS, requestTypeLabel } from '@/utils/leave'

const props = defineProps<{ entry: CalendarEntry }>()

// The type is in the hover text only when the API sent it (HR, the
// requester and their managers).
const title = computed(() => {
  const parts = [props.entry.user.name]
  parts.push(props.entry.leave_type ? requestTypeLabel(props.entry) : KIND_LABELS[props.entry.kind])
  if (props.entry.half_day !== 'none') parts.push(HALF_DAY_LABELS[props.entry.half_day])
  if (props.entry.status === 'pending') parts.push('Waiting for approval')
  return parts.join(' · ')
})
</script>

<style scoped>
.entry {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  max-width: 100%;
  min-height: 22px;
  padding: 0 7px;
  border-radius: 6px;
  font-size: 12px;
  font-weight: 500;
  line-height: 20px;
  border: 1px solid transparent;
  background: rgba(var(--v-theme-primary), 0.16);
  color: rgb(var(--v-theme-on-surface));
}
.entry__name {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.entry__half {
  flex-shrink: 0;
}
.entry--wfh {
  background: transparent;
  border: 1.5px solid rgb(var(--v-theme-primary));
}
.entry--pending {
  background: rgba(var(--v-theme-warning), 0.1);
  border: 1.5px dashed rgb(var(--v-theme-warning));
}
</style>
