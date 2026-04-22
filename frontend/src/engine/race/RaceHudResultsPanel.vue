<script setup lang="ts">
/**
 * RaceHudResultsPanel — placings card shown during the finished phase.
 */
import type { Placing, RaceHudSlot } from './types'

const props = defineProps<{
  placings: readonly Placing[] | null
  slots: readonly RaceHudSlot[]
}>()

/** Map racer-<idx> id to a display name via the slots array. */
function nameForRacer(racerId: string): string {
  const idx = Number(racerId.replace(/^racer-/, ''))
  if (!Number.isNaN(idx) && props.slots[idx]) return props.slots[idx].name
  return racerId
}

function resultLabel(p: Placing): string {
  return p.finished
    ? (p.finishTimeMs / 1000).toFixed(2) + 's'
    : p.distanceM.toFixed(1) + 'm (DNF)'
}
</script>

<template>
  <div class="panel">
    <h2>Results</h2>
    <ol v-if="placings">
      <li v-for="p in placings" :key="p.racerId">
        <span class="place">#{{ p.place }}</span>
        <span class="name">{{ nameForRacer(p.racerId) }}</span>
        <span class="meta">{{ resultLabel(p) }}</span>
      </li>
    </ol>
    <p class="hint">Next round starts shortly…</p>
  </div>
</template>

<style scoped>
.panel {
  position: absolute;
  top: 50%;
  left: 50%;
  transform: translate(-50%, -50%);
  min-width: 380px;
  background: rgba(0, 0, 0, 0.65);
  border-radius: 12px;
  padding: 20px 28px;
  backdrop-filter: blur(4px);
  color: #fff;
  font-family: system-ui, -apple-system, sans-serif;
  text-shadow: 0 2px 4px rgba(0, 0, 0, 0.5);
}
h2 {
  margin: 0 0 16px;
  font-size: 26px;
  text-align: center;
}
ol {
  list-style: none;
  margin: 0 0 16px;
  padding: 0;
}
li {
  display: flex;
  align-items: center;
  gap: 14px;
  padding: 10px 14px;
  background: rgba(255, 255, 255, 0.08);
  border-radius: 8px;
  margin-bottom: 6px;
}
.place {
  font-weight: 800;
  font-size: 20px;
  min-width: 40px;
}
.name {
  flex: 1;
  font-weight: 600;
}
.meta {
  font-variant-numeric: tabular-nums;
  opacity: 0.9;
  font-size: 13px;
}
.hint {
  margin: 0;
  text-align: center;
  opacity: 0.85;
  font-size: 14px;
}
</style>
