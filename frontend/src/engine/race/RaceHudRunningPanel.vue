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

<script setup lang="ts">
/**
 * RaceHudRunningPanel — timer + live progress bars for each racer.
 *
 * Extracted from RaceHUD.vue so the parent component stays under the
 * race-module file-size cap. Purely presentational — all state comes in
 * via props.
 */
import type { RaceHudSlot } from './types'

const props = defineProps<{
  elapsedMs: number
  trackLengthM: number
  slots: readonly RaceHudSlot[]
}>()

function timerLabel(): string {
  return (props.elapsedMs / 1000).toFixed(1)
}

function progressPercent(positionM: number): number {
  return Math.max(0, Math.min(1, positionM / props.trackLengthM)) * 100
}

function paceLabel(slot: RaceHudSlot): string {
  if (slot.finished) return 'finished'
  if (!slot.isMoving) return 'idle'
  return slot.isSprinting ? 'running' : 'walking'
}
</script>

<template>
  <div class="panel">
    <div class="timer">{{ timerLabel() }}s</div>
    <ul>
      <li v-for="(slot, i) in slots" :key="i" :class="{ sprinting: slot.isSprinting && slot.isMoving }">
        <span class="name">{{ slot.name }}</span>
        <div class="progress">
          <div class="progress-fill" :style="{ width: progressPercent(slot.positionM) + '%' }" />
        </div>
        <span class="pace">{{ paceLabel(slot) }}</span>
        <span class="meta">{{ slot.positionM.toFixed(1) }}m</span>
      </li>
    </ul>
  </div>
</template>

<style scoped>
.panel {
  position: absolute;
  top: 24px;
  left: 24px;
  min-width: 420px;
  background: rgba(0, 0, 0, 0.65);
  border-radius: 12px;
  padding: 20px 28px;
  backdrop-filter: blur(4px);
  color: #fff;
  font-family: system-ui, -apple-system, sans-serif;
  text-shadow: 0 2px 4px rgba(0, 0, 0, 0.5);
}
.timer {
  font-size: 34px;
  font-weight: 700;
  margin-bottom: 10px;
  font-variant-numeric: tabular-nums;
}
ul {
  list-style: none;
  margin: 0;
  padding: 0;
  display: flex;
  flex-direction: column;
  gap: 8px;
}
li {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 8px 12px;
  background: rgba(255, 255, 255, 0.08);
  border-radius: 8px;
  transition: background 0.2s;
}
li.sprinting {
  background: rgba(120, 200, 255, 0.25);
}
.name {
  font-weight: 600;
}
.progress {
  flex: 1;
  height: 10px;
  background: rgba(255, 255, 255, 0.15);
  border-radius: 5px;
  overflow: hidden;
}
.progress-fill {
  height: 100%;
  background: linear-gradient(90deg, #ffd75e, #ff6b4a);
  transition: width 0.08s linear;
}
.pace {
  font-size: 11px;
  min-width: 60px;
  text-align: right;
  opacity: 0.85;
  text-transform: uppercase;
  letter-spacing: 0.06em;
}
.meta {
  font-variant-numeric: tabular-nums;
  min-width: 54px;
  text-align: right;
  font-size: 13px;
  opacity: 0.9;
}
</style>
