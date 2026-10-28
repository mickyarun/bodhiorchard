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

<!-- Leave type for a request, as a group of radio cards that each say how
     much of that type is left: on the request's start date once the preview
     has priced the dates (the same number as its before/after line),
     until then what is left today. -->
<template>
  <fieldset class="types">
    <legend class="types__legend">Leave type</legend>
    <p v-if="!balances.length" class="types__empty">HR hasn't added leave types yet.</p>
    <div class="types__grid">
      <label
        v-for="b in balances"
        :key="b.leave_type.id"
        class="types__option"
        :class="{ 'types__option--on': b.leave_type.id === model }"
      >
        <input v-model="model" type="radio" :name="group" :value="b.leave_type.id" class="types__radio" />
        <span class="types__text">
          <span class="types__name">{{ b.leave_type.name }}</span>
          <span class="types__left">{{ leftLabel(b) }}</span>
        </span>
      </label>
    </div>
  </fieldset>
</template>

<script setup lang="ts">
import { useId } from 'vue'
import type { Balance, LeavePreview } from '@/types/leave'
import { formatDays, toNumber } from '@/utils/leave'
import { daysLeftForDraft } from '@/utils/leaveAccrual'

const props = defineProps<{ balances: Balance[]; preview?: LeavePreview | null }>()
const model = defineModel<string | null>({ required: true })
const group = useId()

function leftLabel(b: Balance): string {
  const available = daysLeftForDraft(b, props.preview ?? null)
  if (available === null) return 'No limit'
  const left = toNumber(available)
  return `${formatDays(left)} ${left === 1 ? 'day' : 'days'} left`
}
</script>

<style scoped>
.types {
  border: 0;
  margin: 0;
  padding: 0;
  min-width: 0;
}
.types__legend {
  font-size: var(--text-sm);
  font-weight: 500;
  margin-bottom: 8px;
}
.types__empty {
  margin: 0;
  font-size: var(--text-sm);
  color: rgb(var(--v-theme-on-surface-variant));
}
.types__grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(140px, 1fr));
  gap: 8px;
}
.types__option {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 10px 12px;
  border-radius: 10px;
  border: 1px solid rgb(var(--v-theme-rule));
  background: rgb(var(--v-theme-surface));
  cursor: pointer;
  min-width: 0;
}
.types__option:hover {
  background: rgb(var(--v-theme-surface-variant));
}
.types__option--on,
.types__option--on:hover {
  border: 2px solid rgb(var(--v-theme-primary));
  padding: 9px 11px;
  background: rgba(var(--v-theme-primary), 0.06);
}
.types__option:has(:focus-visible) {
  outline: 2px solid var(--color-focus);
  outline-offset: 2px;
}
.types__radio {
  margin: 0;
  accent-color: rgb(var(--v-theme-primary));
  flex-shrink: 0;
}
.types__text {
  display: flex;
  flex-direction: column;
  min-width: 0;
}
.types__name {
  font-size: var(--text-sm);
  font-weight: 500;
}
.types__left {
  font-size: 12px;
  color: rgb(var(--v-theme-on-surface-variant));
}
</style>
