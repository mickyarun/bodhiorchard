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

<!-- One balance tile: a big number, a thin meter (used solid, pending
     lighter), a caption and an optional note under it. Presentational;
     BalanceGrid maps data in. -->
<template>
  <div
    class="balance-card"
    :class="{ 'balance-card--compact': compact, 'balance-card--highlight': highlight }"
  >
    <div class="balance-card__head">
      <span class="balance-card__dot" :style="{ background: tone }" aria-hidden="true" />
      <span class="balance-card__title">{{ title }}</span>
      <v-chip v-if="tag" size="x-small" variant="tonal" class="ml-auto">{{ tag }}</v-chip>
    </div>
    <div class="balance-card__figure">
      <span class="balance-card__value">{{ value }}</span>
      <span v-if="unit" class="balance-card__unit">{{ unit }}</span>
    </div>
    <div v-if="meter" class="balance-card__meter" role="img" :aria-label="caption">
      <span class="balance-card__used" :style="{ width: `${meter.used}%`, background: tone }" />
      <span
        class="balance-card__pending"
        :style="{ width: `${meter.pending}%`, background: tone }"
      />
    </div>
    <div class="balance-card__caption">{{ caption }}</div>
    <div v-if="note" class="balance-card__caption">{{ note }}</div>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'

const props = defineProps<{
  title: string
  /** Theme colour name, e.g. 'info'. */
  color: string
  value: string
  unit?: string
  meter: { used: number; pending: number } | null
  caption: string
  /** A second, quieter line, e.g. why "days left" counts later earning. */
  note?: string
  tag?: string
  /** Smaller, tinted tile for use inside another card. */
  compact?: boolean
  highlight?: boolean
}>()

const tone = computed(() => `rgb(var(--v-theme-${props.color}))`)
</script>

<style scoped>
.balance-card {
  background: rgb(var(--v-theme-surface));
  border: 1px solid rgb(var(--v-theme-rule));
  border-radius: 12px;
  padding: 18px 20px;
  display: flex;
  flex-direction: column;
  gap: 10px;
  min-width: 0;
}
.balance-card__head {
  display: flex;
  align-items: center;
  gap: 8px;
  min-width: 0;
}
.balance-card__dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  flex-shrink: 0;
}
.balance-card__title {
  font-size: var(--text-sm);
  font-weight: 500;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.balance-card__figure {
  display: flex;
  align-items: baseline;
  flex-wrap: wrap;
  gap: 6px;
}
.balance-card__value {
  font-size: 32px;
  line-height: 36px;
  font-weight: 600;
  letter-spacing: var(--tracking-display);
}
.balance-card__unit,
.balance-card__caption {
  font-size: 13px;
  color: rgb(var(--v-theme-on-surface-variant));
}
.balance-card__meter {
  display: flex;
  height: 6px;
  border-radius: 999px;
  overflow: hidden;
  background: rgb(var(--v-theme-surface-variant));
}
.balance-card__pending {
  opacity: 0.4;
}
.balance-card--compact {
  padding: 12px 14px;
  gap: 6px;
  background: rgb(var(--v-theme-surface-variant));
  border-color: transparent;
}
.balance-card--compact .balance-card__value {
  font-size: 22px;
  line-height: 28px;
}
.balance-card--compact .balance-card__meter {
  height: 4px;
  background: rgb(var(--v-theme-rule));
}
@media (max-width: 600px) {
  .balance-card {
    padding: 14px;
    gap: 8px;
  }
  .balance-card__value {
    font-size: 26px;
    line-height: 30px;
  }
}
.balance-card--highlight {
  border-color: rgb(var(--v-theme-primary));
  background: rgba(var(--v-theme-primary), 0.06);
}
</style>
