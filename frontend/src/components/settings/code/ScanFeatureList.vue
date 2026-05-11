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
  Reviewable list of synthesized features attached to a scan step
  (FEATURE_SYNTHESIS / FEATURE_MERGE). Pure presentational — the
  parent (ScanChipPopover) decides when to show it.

  Each item shows the canonical title + a 2-line clamped description
  (full text on hover) and a merge-outcome chip when set.
-->
<template>
  <section class="features">
    <h4 class="features__title">
      Features produced
      <span class="features__count">{{ features.length }}</span>
    </h4>
    <ul class="features__list">
      <li
        v-for="feat in features"
        :key="feat.title"
        class="features__item"
      >
        <div class="features__head">
          <span class="features__name">{{ feat.title }}</span>
          <v-chip
            v-if="feat.merge_outcome"
            size="x-small"
            variant="tonal"
            :color="chipColor(feat.merge_outcome)"
          >
            {{ feat.merge_outcome }}
          </v-chip>
        </div>
        <p
          v-if="feat.description"
          class="features__desc"
          :title="feat.description"
        >
          {{ feat.description }}
        </p>
      </li>
    </ul>
  </section>
</template>

<script setup lang="ts">
export interface ProducedFeature {
  title: string
  description: string
  merge_outcome: string | null
}

defineProps<{ features: ProducedFeature[] }>()

function chipColor(outcome: string): string {
  if (outcome === 'CANONICAL') return 'success'
  if (outcome === 'MERGED_INTO') return 'info'
  if (outcome === 'UNVISITED') return 'warning'
  return 'grey'
}
</script>

<style scoped>
.features {
  display: flex;
  flex-direction: column;
  gap: 6px;
}
.features__title {
  margin: 0;
  font-size: 0.7rem;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.06em;
  color: rgba(var(--v-theme-on-surface), 0.55);
  display: flex;
  align-items: center;
  gap: 6px;
}
.features__count {
  font-weight: 500;
  color: rgba(var(--v-theme-on-surface), 0.45);
  letter-spacing: normal;
}
.features__list {
  list-style: none;
  padding: 6px;
  margin: 0;
  display: flex;
  flex-direction: column;
  gap: 6px;
  max-height: 320px;
  overflow-y: auto;
  border: 1px solid rgba(var(--v-theme-on-surface), 0.08);
  border-radius: 6px;
  background: rgba(var(--v-theme-on-surface), 0.04);
}
.features__item {
  display: flex;
  flex-direction: column;
  gap: 2px;
  padding: 6px 8px;
  border-radius: 4px;
  background: rgb(var(--v-theme-surface));
}
.features__head {
  display: flex;
  align-items: center;
  gap: 8px;
  justify-content: space-between;
}
.features__name {
  font-size: 0.82rem;
  font-weight: 500;
  color: rgba(var(--v-theme-on-surface), 0.92);
  word-break: break-word;
}
.features__desc {
  margin: 0;
  font-size: 0.72rem;
  color: rgba(var(--v-theme-on-surface), 0.6);
  /* clamp to 2 lines so the popover stays scannable; full text on hover */
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
}
</style>
