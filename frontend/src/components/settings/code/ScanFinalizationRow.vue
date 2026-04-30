<!--
  SPDX-License-Identifier: AGPL-3.0-or-later
  Copyright (C) 2026 Arun Rajkumar

  Cross-repo finalization strip rendered once below the repo rows
  during a scan. The four global phases run a single time across the
  whole scan, so showing them on every repo lane (the way the legacy
  ScanTimeline does) misleads the user into thinking they're per-repo.

  Status per phase is read from the first repo_run that has a row for
  it — backend writes identical step rows for every repo since the
  phase is shared.
-->
<template>
  <div class="finalization">
    <div class="finalization__head">
      <v-icon icon="mdi-flag-checkered" size="14" class="finalization__icon" />
      <span class="finalization__title">Finalization · cross-repo</span>
    </div>
    <ol class="finalization__dots">
      <li v-for="phase in GLOBAL_PHASES" :key="phase" class="finalization__item">
        <ScanChipPopover :phase="phase" :step="stepFor(phase)" />
        <span class="finalization__label">{{ phase }}</span>
      </li>
    </ol>
  </div>
</template>

<script setup lang="ts">
import ScanChipPopover from './ScanChipPopover.vue'
import type { RepoRunRow, ScanPhase, StepRow } from '@/stores/reposcanv2Scans'

// When adding a new phase, classify it here and in ScanRowTrack.vue.
const GLOBAL_PHASES: ScanPhase[] = [
  'feature_merge',
  'skill_remap',
  'embedding_backfill',
  'persist_results',
]

const props = defineProps<{ runs: RepoRunRow[] }>()

function stepFor(phase: ScanPhase): StepRow | null {
  for (const run of props.runs) {
    const step = run.steps.find(s => s.phase === phase)
    if (step) return step
  }
  return null
}
</script>

<style scoped>
.finalization {
  display: flex;
  flex-direction: column;
  gap: 8px;
  padding: 12px 20px 16px;
  /* Sticky to the bottom of the scroll container so the four global
     phase chips remain visible while the user scrolls through long
     repo lists. Solid background (the page surface tinted by 2%
     overlay below it) prevents content bleed-through during scroll
     overlap; z-index sits below the sticky header to avoid stacking
     conflicts at the very ends of the list. */
  position: sticky;
  bottom: 0;
  z-index: 2;
  background:
    linear-gradient(rgba(var(--v-theme-on-surface), 0.02), rgba(var(--v-theme-on-surface), 0.02)),
    rgb(var(--v-theme-surface));
  border-top: 1px solid rgba(var(--v-theme-on-surface), 0.06);
}
.finalization__head {
  display: flex; align-items: center; gap: 6px;
  font-size: 0.72rem;
  color: rgba(var(--v-theme-on-surface), 0.55);
  text-transform: uppercase;
  letter-spacing: 0.06em;
}
.finalization__icon { opacity: 0.6; }
.finalization__title { font-weight: 600; }
.finalization__dots {
  list-style: none;
  padding: 0;
  margin: 0;
  display: flex;
  flex-wrap: wrap;
  gap: 14px;
}
.finalization__item {
  display: inline-flex;
  align-items: center;
  gap: 6px;
}
.finalization__label {
  font-size: 0.72rem;
  font-family: var(--v-font-family-monospace, monospace);
  color: rgba(var(--v-theme-on-surface), 0.65);
}
</style>
