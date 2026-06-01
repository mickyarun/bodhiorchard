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

<!--
  Phases whose median drift across the last 50 closes is above the
  +30% threshold. Each row gets a red-tinted background, a large
  drift percentage, and a horizontal bar visualizing how many of the
  recent BUDs overran. Parent controls whether to render this card —
  empty arrays show nothing rather than an empty heading.
-->

<template>
  <section class="card">
    <header class="card__head">
      <v-icon icon="mdi-alert-circle-outline" size="18" color="warning" />
      <div class="card__title">Repeat-offender phases</div>
      <div class="card__sub">
        Phases whose median drift across the last 50 closes is above
        the +30% threshold the recap also uses to flag drift.
      </div>
    </header>
    <div class="list">
      <article
        v-for="row in offenders"
        :key="row.phase"
        class="offender"
      >
        <div class="offender-phase">{{ row.phase }}</div>
        <div class="offender-drift">
          +{{ row.median_drift_pct.toFixed(0) }}%
          <span class="offender-drift__label">median drift</span>
        </div>
        <div class="offender-ratio">
          {{ row.buds_over_estimate }} of {{ row.buds_total }} BUDs
          over estimate
        </div>
        <div class="offender-bar">
          <div
            class="offender-bar__fill"
            :style="{
              width: `${(row.buds_over_estimate / Math.max(1, row.buds_total)) * 100}%`,
            }"
          />
        </div>
      </article>
    </div>
  </section>
</template>

<script setup lang="ts">
import type { RepeatOffender } from '@/composables/useLearningsOverview'

defineProps<{ offenders: RepeatOffender[] }>()
</script>

<style scoped>
.card {
  border: 1px solid rgba(var(--v-theme-on-surface), 0.08);
  border-radius: 12px;
  padding: 18px 20px 20px;
  background: rgba(var(--v-theme-surface-variant), 0.04);
}

.card__head {
  display: grid;
  grid-template-columns: auto 1fr;
  column-gap: 10px;
  row-gap: 2px;
  margin-bottom: 14px;
}

.card__head > .v-icon {
  grid-row: 1 / span 2;
  align-self: start;
  margin-top: 2px;
}

.card__title {
  font-size: 15px;
  font-weight: 500;
}

.card__sub {
  font-size: 12px;
  color: rgb(var(--v-theme-on-surface-variant));
  opacity: 0.85;
  max-width: 720px;
}

.list {
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.offender {
  display: grid;
  grid-template-columns: 140px auto 1fr;
  grid-template-rows: auto auto;
  column-gap: 16px;
  row-gap: 4px;
  align-items: baseline;
  padding: 10px 12px;
  border: 1px solid rgba(var(--v-theme-error), 0.16);
  border-radius: 8px;
  background: rgba(var(--v-theme-error), 0.05);
}

.offender-phase {
  font-size: 13px;
  font-weight: 500;
  grid-row: 1 / span 2;
  align-self: center;
}

.offender-drift {
  font-size: 18px;
  font-weight: 500;
  color: rgb(var(--v-theme-error));
  font-variant-numeric: tabular-nums;
}

.offender-drift__label {
  font-size: 11px;
  font-weight: 400;
  color: rgb(var(--v-theme-on-surface-variant));
  margin-left: 6px;
}

.offender-ratio {
  font-size: 12px;
  color: rgb(var(--v-theme-on-surface-variant));
  grid-row: 2;
  grid-column: 2;
}

.offender-bar {
  grid-row: 1 / span 2;
  align-self: center;
  height: 6px;
  background: rgba(var(--v-theme-error), 0.12);
  border-radius: 3px;
  overflow: hidden;
  max-width: 240px;
}

.offender-bar__fill {
  height: 100%;
  background: rgb(var(--v-theme-error));
  opacity: 0.7;
  transition: width 0.2s ease;
}
</style>
