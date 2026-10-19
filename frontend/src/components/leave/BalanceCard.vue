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
     lighter) and a caption. Presentational; BalanceGrid maps data in. -->
<template>
  <v-card color="surface" rounded="lg" class="pa-4 balance-card">
    <div class="d-flex align-center ga-2 mb-3">
      <span class="balance-card__dot" :style="{ background: tone }" aria-hidden="true" />
      <span class="text-body-2 font-weight-medium text-truncate">{{ title }}</span>
      <v-chip v-if="tag" size="x-small" variant="tonal" class="ml-auto">{{ tag }}</v-chip>
    </div>
    <div class="d-flex align-baseline ga-2">
      <span class="balance-card__value bo-display">{{ value }}</span>
      <span v-if="unit" class="text-caption text-medium-emphasis">{{ unit }}</span>
    </div>
    <div v-if="meter" class="balance-card__meter mt-3" role="img" :aria-label="caption">
      <span class="balance-card__used" :style="{ width: `${meter.used}%`, background: tone }" />
      <span
        class="balance-card__pending"
        :style="{ width: `${meter.pending}%`, background: tone }"
      />
    </div>
    <div class="text-caption text-medium-emphasis mt-2">{{ caption }}</div>
  </v-card>
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
  tag?: string
}>()

const tone = computed(() => `rgb(var(--v-theme-${props.color}))`)
</script>

<style scoped>
.balance-card__dot {
  width: 10px;
  height: 10px;
  border-radius: 50%;
  flex-shrink: 0;
}
.balance-card__value {
  font-size: 28px;
  font-weight: 700;
  line-height: 1;
}
.balance-card__meter {
  display: flex;
  height: 4px;
  border-radius: 999px;
  overflow: hidden;
  background: rgba(var(--v-theme-on-surface), 0.08);
}
.balance-card__pending {
  opacity: 0.4;
}
</style>
