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

<!-- Someone out on the team calendar. Leave is a tinted chip, WFH a
     dashed outline; pending requests are faded with a dashed border.
     The type colour only shows when the API sent the type. -->
<template>
  <span
    class="entry"
    :class="{
      'entry--wfh': entry.kind === 'wfh',
      'entry--pending': entry.status === 'pending',
    }"
    :style="{ '--entry-tone': tone }"
    :title="title"
  >
    <v-icon v-if="entry.kind === 'wfh'" icon="mdi-home-outline" size="12" />
    <span class="entry__name">{{ firstName(entry.user.name) }}</span>
    <span v-if="entry.half_day !== 'none'" aria-hidden="true">◐</span>
  </span>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import type { CalendarEntry } from '@/types/leave'
import { firstName, HALF_DAY_LABELS, KIND_LABELS, requestTypeLabel, swatchColor } from '@/utils/leave'

const props = defineProps<{ entry: CalendarEntry }>()

const tone = computed(() => {
  if (props.entry.kind === 'wfh') return 'var(--v-theme-primary)'
  if (props.entry.leave_type) return `var(--v-theme-${swatchColor(props.entry.leave_type.color_key)})`
  return 'var(--v-theme-info)'
})

const title = computed(() => {
  const parts = [props.entry.user.name]
  parts.push(props.entry.leave_type ? requestTypeLabel(props.entry) : KIND_LABELS[props.entry.kind])
  if (props.entry.half_day !== 'none') parts.push(HALF_DAY_LABELS[props.entry.half_day])
  if (props.entry.status === 'pending') parts.push('Pending')
  return parts.join(' · ')
})
</script>

<style scoped>
.entry {
  display: inline-flex;
  align-items: center;
  gap: 3px;
  max-width: 100%;
  padding: 1px 6px;
  border-radius: 6px;
  font-size: 11px;
  line-height: 16px;
  border: 1px solid transparent;
  background: rgba(var(--entry-tone), 0.16);
  color: rgb(var(--v-theme-on-surface));
}
.entry__name {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.entry--wfh {
  background: transparent;
  border: 1px dashed rgb(var(--entry-tone));
}
.entry--pending {
  opacity: 0.5;
  border-style: dashed;
  border-color: rgb(var(--entry-tone));
}
</style>
