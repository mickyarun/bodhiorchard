<!--
  SPDX-License-Identifier: AGPL-3.0-or-later
  Copyright (C) 2026 Arun Rajkumar

  Compact trail of sub-stages collapsed under one phase chip. Multi-
  stage phases (notably CODE_INDEX, which rolls up ingest →
  extract → merge_labels → filter_infra → hierarchical → size_floor →
  top_n) re-stamp the same chip; without this trail the user only sees
  the last stage's numbers.

  Each row shows the sub-stage's reduction line and (when relevant) the
  reason it skipped. Pure presentational.
-->
<template>
  <section class="trail">
    <h4 class="trail__title">
      Pipeline trail
      <span class="trail__count">{{ stages.length }}</span>
    </h4>
    <ol class="trail__list">
      <li
        v-for="stage in stages"
        :key="stage.name"
        class="trail__item"
        :class="`trail__item--${stage.status}`"
      >
        <div class="trail__head">
          <span class="trail__name">{{ stage.name }}</span>
          <span class="trail__counts">
            {{ stage.input_count }} → {{ stage.kept_count }}
            <span v-if="stage.dropped_count" class="trail__dropped">
              / {{ stage.dropped_count }}
            </span>
          </span>
        </div>
        <div v-if="stage.io_label" class="trail__io">{{ stage.io_label }}</div>
        <div v-if="stage.skipped_reason" class="trail__skipped">
          <v-icon icon="mdi-skip-next-circle-outline" size="11" />
          {{ stage.skipped_reason }}
        </div>
      </li>
    </ol>
  </section>
</template>

<script setup lang="ts">
export interface SubStage {
  name: string
  status: 'done' | 'skipped_cache'
  input_count: number
  kept_count: number
  dropped_count: number
  io_label: string | null
  skipped_reason: string | null
  duration_ms: number | null
}

defineProps<{ stages: SubStage[] }>()
</script>

<style scoped>
.trail { display: flex; flex-direction: column; gap: 6px; }
.trail__title {
  margin: 0; font-size: 0.7rem; font-weight: 600;
  text-transform: uppercase; letter-spacing: 0.06em;
  color: rgba(var(--v-theme-on-surface), 0.55);
  display: flex; align-items: center; gap: 6px;
}
.trail__count {
  font-weight: 500;
  color: rgba(var(--v-theme-on-surface), 0.45);
  letter-spacing: normal;
}
.trail__list {
  list-style: none;
  padding: 6px;
  margin: 0;
  display: flex;
  flex-direction: column;
  gap: 4px;
  max-height: 280px;
  overflow-y: auto;
  border: 1px solid rgba(var(--v-theme-on-surface), 0.08);
  border-radius: 6px;
  background: rgba(var(--v-theme-on-surface), 0.04);
}
.trail__item {
  display: flex; flex-direction: column; gap: 2px;
  padding: 6px 8px;
  border-radius: 4px;
  background: rgb(var(--v-theme-surface));
  border-left: 2px solid transparent;
}
.trail__item--done { border-left-color: rgb(var(--v-theme-success)); }
.trail__item--skipped_cache { border-left-color: rgb(var(--v-theme-info)); }
.trail__head {
  display: flex; align-items: center; justify-content: space-between; gap: 8px;
}
.trail__name {
  font-family: var(--v-font-family-monospace, monospace);
  font-size: 0.78rem;
  color: rgba(var(--v-theme-on-surface), 0.92);
}
.trail__counts {
  font-family: var(--v-font-family-monospace, monospace);
  font-size: 0.76rem;
  color: rgba(var(--v-theme-on-surface), 0.85);
  white-space: nowrap;
}
.trail__dropped {
  color: rgba(var(--v-theme-on-surface), 0.55);
}
.trail__io {
  font-size: 0.7rem;
  color: rgba(var(--v-theme-on-surface), 0.55);
}
.trail__skipped {
  display: flex; align-items: center; gap: 4px;
  font-size: 0.7rem;
  color: rgb(var(--v-theme-info));
}
</style>
