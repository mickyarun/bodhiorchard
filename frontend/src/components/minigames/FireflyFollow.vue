<!--
  Copyright 2025-2026 Arun Rajkumar

  Licensed under the Apache License, Version 2.0 (the "License");
  you may not use this file except in compliance with the License.
  You may obtain a copy of the License at

      http://www.apache.org/licenses/LICENSE-2.0

  Unless required by applicable law or agreed to in writing, software
  distributed under the License is distributed on an "AS IS" BASIS,
  WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
  See the License for the specific language governing permissions and
  limitations under the License.

  FireflyFollow — watch the fireflies light up, then repeat the sequence.

  Each cleared level adds one flash (longer) and quickens the playback
  (faster). A wrong tap ends the run. Rules live in @shared/minigames/firefly;
  this component owns timing, rendering, and the glow.
-->
<template>
  <div class="firefly d-flex flex-column ga-3">
    <div class="firefly__hud d-flex align-center justify-space-between">
      <span class="firefly__status" :class="`firefly__status--${phase}`">{{ statusText }}</span>
      <span class="firefly__level">Lv {{ level }} <small>· best {{ score }}</small></span>
    </div>

    <div class="firefly__stage" :class="{ 'firefly__stage--shake': shake }">
      <span v-for="n in 9" :key="n" class="firefly__amb" :style="ambStyle(n)" />

      <div class="firefly__grid" :class="{ 'firefly__grid--watch': phase === 'watch' }">
        <button
          v-for="pad in PADS"
          :key="pad.id"
          class="firefly__pad"
          :class="{
            'firefly__pad--lit': lit === pad.id,
            'firefly__pad--wrong': wrongPad === pad.id,
          }"
          :style="{ '--pad': pad.color }"
          :disabled="phase !== 'input'"
          :aria-label="pad.id"
          @pointerdown.prevent="tap(pad.id)"
        >
          <span class="firefly__glyph">{{ pad.glyph }}</span>
        </button>
      </div>

      <div v-if="phase === 'levelup'" class="firefly__shimmer" />

      <div v-if="phase === 'over'" class="firefly__overlay">
        <span class="firefly__overlay-emoji">✨</span>
        <div class="text-h6 font-weight-bold mb-1">
          You cleared {{ score }} {{ score === 1 ? 'level' : 'levels' }}!
        </div>
        <v-btn color="primary" rounded="lg" @click="collect">
          Collect points
        </v-btn>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, onUnmounted, ref } from 'vue'
import { PADS, type PadId } from '@shared/minigames/firefly'
import type { MinigameResult } from '@/multiplayer/MinigameRoomClient'
import { useMinigameRoom } from './useMinigameRoom'

const emit = defineEmits<{ finished: [result: MinigameResult | null] }>()

// Local *rendering* phase, distinct from the server's playing/finished. The
// server owns the sequence + score; this only decides what the board shows.
type Phase = 'connecting' | 'watch' | 'input' | 'levelup' | 'over'

const phase = ref<Phase>('connecting')
const lit = ref<PadId | null>(null)
const wrongPad = ref<PadId | null>(null)
const shake = ref(false)
const result = ref<MinigameResult | null>(null)

const room = useMinigameRoom('firefly', { onEvent, onResult })
const score = room.score // cleared levels (authoritative)
const level = room.round // current round being played

const statusText = computed(() => {
  switch (phase.value) {
    case 'connecting':
      return 'Connecting…'
    case 'watch':
      return 'Watch…'
    case 'input':
      return 'Your turn'
    case 'levelup':
      return 'Nice!'
    default:
      return 'Game over'
  }
})

// A run generation: bumping it abandons any in-flight playback (new round/unmount).
let runId = 0
const timers = new Set<number>()
function sleep(ms: number): Promise<void> {
  return new Promise((resolve) => {
    const id = window.setTimeout(() => {
      timers.delete(id)
      resolve()
    }, ms)
    timers.add(id)
  })
}
function clearTimers(): void {
  for (const id of timers) window.clearTimeout(id)
  timers.clear()
}

/** Render the server-sent sequence, then hand control to the player. */
async function playback(sequence: PadId[], flashMs: number): Promise<void> {
  const myRun = ++runId
  phase.value = 'watch'
  lit.value = null
  wrongPad.value = null
  const gap = Math.max(120, Math.round(flashMs * 0.4))
  await sleep(420)
  for (const pad of sequence) {
    if (myRun !== runId) return
    lit.value = pad
    await sleep(flashMs)
    if (myRun !== runId) return
    lit.value = null
    await sleep(gap)
  }
  if (myRun !== runId) return
  phase.value = 'input'
}

function onEvent(type: string, payload: unknown): void {
  if (type === 'firefly_sequence') {
    const { sequence, flashMs } = payload as { sequence: PadId[]; flashMs: number }
    void playback(sequence, flashMs)
  } else if (type === 'firefly_result') {
    const { result: outcome, padId } = payload as { result: string; padId?: PadId }
    if (outcome === 'wrong') {
      runId++ // abandon any pending playback
      clearTimers()
      phase.value = 'over'
      wrongPad.value = padId ?? null
      shake.value = true
      void sleep(420).then(() => (shake.value = false))
    } else if (outcome === 'levelup') {
      phase.value = 'levelup' // the next firefly_sequence resets to 'watch'
    }
  }
}

function onResult(r: MinigameResult): void {
  result.value = r
  phase.value = 'over'
}

function tap(pad: PadId): void {
  if (phase.value !== 'input') return
  lit.value = pad // optimistic glow; the server confirms via firefly_result
  void sleep(160).then(() => {
    if (lit.value === pad) lit.value = null
  })
  room.send('tap', { padId: pad })
}

function collect(): void {
  emit('finished', result.value)
}

/** Stable-but-scattered placement for the ambient firefly specks. */
function ambStyle(n: number): Record<string, string> {
  const x = (n * 37) % 100
  const y = (n * 53) % 100
  return {
    left: `${x}%`,
    top: `${y}%`,
    animationDelay: `${(n % 5) * 0.7}s`,
    animationDuration: `${4 + (n % 4)}s`,
  }
}

onUnmounted(() => {
  runId++
  clearTimers()
})
</script>

<style scoped>
.firefly__hud {
  font-size: 14px;
}
.firefly__status {
  font-weight: 700;
  letter-spacing: 0.02em;
  transition: color 0.2s;
}
.firefly__status--watch {
  color: #b8c0ff;
}
.firefly__status--input {
  color: #74e8a8;
  animation: invite 1.1s ease-in-out infinite;
}
.firefly__status--levelup {
  color: #ffd166;
}
.firefly__status--over {
  color: #ff8087;
}
.firefly__level {
  font-weight: 800;
  font-variant-numeric: tabular-nums;
}
.firefly__level small {
  opacity: 0.65;
  font-weight: 600;
}

.firefly__stage {
  position: relative;
  /* Taps stay taps — don't let a touch-drag here pan/scroll the garden behind. */
  touch-action: none;
  width: 100%;
  height: 340px;
  border-radius: 18px;
  overflow: hidden;
  display: flex;
  align-items: center;
  justify-content: center;
  background:
    radial-gradient(ellipse 80% 60% at 50% 35%, rgba(70, 60, 130, 0.45), transparent 70%),
    linear-gradient(170deg, #1a1840 0%, #14122e 55%, #0b0a1c 100%);
  box-shadow: inset 0 6px 26px rgba(0, 0, 0, 0.5);
}
.firefly__stage--shake {
  animation: shake 0.4s ease;
}

.firefly__amb {
  position: absolute;
  width: 5px;
  height: 5px;
  border-radius: 50%;
  background: radial-gradient(circle, rgba(214, 255, 161, 0.95), rgba(160, 230, 90, 0));
  filter: blur(0.5px);
  animation: drift linear infinite;
  pointer-events: none;
}

.firefly__grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 16px;
  width: 240px;
  height: 240px;
  transition: opacity 0.25s;
}
.firefly__grid--watch {
  opacity: 0.96;
}

.firefly__pad {
  position: relative;
  border: 1px solid rgba(255, 255, 255, 0.1);
  border-radius: 18px;
  cursor: pointer;
  background:
    radial-gradient(circle at 50% 38%, color-mix(in srgb, var(--pad) 55%, #0b0a1c), #0b0a1c 78%);
  filter: saturate(0.55) brightness(0.72);
  transition: filter 0.16s ease, transform 0.16s ease, box-shadow 0.16s ease;
}
.firefly__pad:disabled {
  cursor: default;
}
.firefly__pad:not(:disabled):active {
  transform: scale(0.96);
}
.firefly__glyph {
  font-size: 24px;
  color: #fff;
  opacity: 0.28;
  text-shadow: 0 1px 3px rgba(0, 0, 0, 0.6);
  transition: opacity 0.16s;
}
.firefly__pad--lit {
  filter: saturate(1.25) brightness(1.25);
  transform: scale(1.06);
  background: radial-gradient(circle at 50% 40%, var(--pad), color-mix(in srgb, var(--pad) 35%, #0b0a1c) 82%);
  box-shadow:
    0 0 18px 2px color-mix(in srgb, var(--pad) 75%, transparent),
    0 0 42px 8px color-mix(in srgb, var(--pad) 45%, transparent);
}
.firefly__pad--lit .firefly__glyph {
  opacity: 0.92;
}
.firefly__pad--wrong {
  filter: saturate(1.4) brightness(1.1);
  background: radial-gradient(circle at 50% 40%, #ff5d6c, #3a0d14 82%);
  box-shadow: 0 0 22px 4px rgba(255, 80, 90, 0.7);
}

.firefly__shimmer {
  position: absolute;
  inset: 0;
  pointer-events: none;
  background: linear-gradient(120deg, transparent 30%, rgba(255, 224, 130, 0.28) 50%, transparent 70%);
  background-size: 240% 100%;
  animation: shimmer 0.62s ease-out;
}

.firefly__overlay {
  position: absolute;
  inset: 0;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 6px;
  color: #fff;
  background: rgba(11, 10, 28, 0.82);
  backdrop-filter: blur(2px);
  animation: rise 0.28s ease-out;
}
.firefly__overlay-emoji {
  font-size: 44px;
  filter: drop-shadow(0 0 12px rgba(255, 224, 130, 0.8));
}

@keyframes drift {
  0% { transform: translate(0, 0); opacity: 0.2; }
  50% { opacity: 0.9; }
  100% { transform: translate(14px, -22px); opacity: 0.2; }
}
@keyframes invite {
  0%, 100% { opacity: 0.7; }
  50% { opacity: 1; }
}
@keyframes shimmer {
  0% { background-position: 140% 0; }
  100% { background-position: -140% 0; }
}
@keyframes shake {
  0%, 100% { transform: translateX(0); }
  20% { transform: translateX(-9px); }
  40% { transform: translateX(8px); }
  60% { transform: translateX(-6px); }
  80% { transform: translateX(4px); }
}
@keyframes rise {
  0% { transform: translateY(10px); opacity: 0; }
  100% { transform: translateY(0); opacity: 1; }
}

@media (prefers-reduced-motion: reduce) {
  .firefly__amb,
  .firefly__stage--shake,
  .firefly__shimmer,
  .firefly__status--input {
    animation: none;
  }
}
</style>
