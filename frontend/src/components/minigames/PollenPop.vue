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

  PollenPop — pop the drifting blossoms before the clock runs out.

  25 seconds; blossoms rise through the meadow air; each pop is a point.
-->
<template>
  <div class="pollen d-flex flex-column ga-3">
    <div class="d-flex align-center justify-space-between">
      <div class="pollen__timer" :class="{ 'pollen__timer--low': timeLeft <= 5 && !done }">
        ⏱ {{ timeLeft.toFixed(0) }}s
        <span class="pollen__timer-bar" :style="{ width: `${(timeLeft / GAME_SECONDS) * 100}%` }" />
      </div>
      <span class="pollen__score">{{ score }} <small>popped</small></span>
    </div>

    <div ref="arena" class="pollen__arena">
      <button
        v-for="m in motes"
        :key="m.id"
        class="pollen__mote"
        :style="{ left: `${m.x}%`, top: `${m.y}%`, fontSize: `${22 * m.scale}px` }"
        @pointerdown="pop(m.id, $event)"
      >
        {{ m.emoji }}
      </button>

      <span
        v-for="p in pops"
        :key="p.id"
        class="pollen__pop"
        :style="{ left: `${p.x}%`, top: `${p.y}%` }"
      >+1</span>

      <div v-if="done" class="pollen__overlay">
        <span class="pollen__overlay-emoji">🌼</span>
        <div class="text-h6 font-weight-bold mb-1">You popped {{ score }}!</div>
        <v-btn color="success" rounded="lg" @click="collect">
          Collect points
        </v-btn>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref } from 'vue'
import { GAME_SECONDS, MOTE_EMOJI } from '@shared/minigames/pollen'
import type { MinigameResult } from '@/multiplayer/MinigameRoomClient'
import { useMinigameRoom } from './useMinigameRoom'

const emit = defineEmits<{ finished: [result: MinigameResult | null] }>()

// A mote the server spawned; rendered locally from the moment it arrived, so
// the visual tracks the server's deterministic motion (minus latency). Pops are
// validated server-side, so the score is authoritative regardless.
interface RenderMote {
  id: number
  x: number // current render x (percent)
  y: number // current render y (percent)
  scale: number
  emoji: string
  vx: number
  vy: number
  x0: number
  start: number // local performance.now() at receipt
}

const motes = ref<RenderMote[]>([])
const pops = ref<Array<{ id: number; x: number; y: number }>>([])
const timeLeft = ref(GAME_SECONDS)
const arena = ref<HTMLElement | null>(null)
const result = ref<MinigameResult | null>(null)

const room = useMinigameRoom('pollen_pop', { onEvent, onResult })
const score = room.score // authoritative count of valid pops
const done = computed(() => room.status.value === 'finished')

let raf = 0
let durationMs = GAME_SECONDS * 1000
let startLocal = 0
let popSeq = 1

function onEvent(type: string, payload: unknown): void {
  if (type === 'pollen_start') {
    durationMs = (payload as { durationMs: number }).durationMs
    startLocal = performance.now()
    timeLeft.value = durationMs / 1000
  } else if (type === 'pollen_spawn') {
    const m = payload as { id: number; x: number; vx: number; vy: number; scale: number; emojiIndex: number }
    motes.value.push({
      id: m.id,
      x: m.x,
      y: 104,
      scale: m.scale,
      emoji: MOTE_EMOJI[m.emojiIndex] ?? MOTE_EMOJI[0],
      vx: m.vx,
      vy: m.vy,
      x0: m.x,
      start: performance.now(),
    })
  } else if (type === 'pollen_despawn') {
    const { id } = payload as { id: number }
    motes.value = motes.value.filter((m) => m.id !== id)
  } else if (type === 'pollen_popped') {
    const { id } = payload as { id: number }
    motes.value = motes.value.filter((m) => m.id !== id)
  }
}

function onResult(r: MinigameResult): void {
  result.value = r
  motes.value = []
}

function pop(id: number, _ev: PointerEvent): void {
  if (done.value) return
  const m = motes.value.find((mote) => mote.id === id)
  if (!m) return
  // Optimistic removal + feedback; the score itself comes from the server.
  motes.value = motes.value.filter((mote) => mote.id !== id)
  const popId = popSeq++
  pops.value.push({ id: popId, x: m.x, y: m.y })
  window.setTimeout(() => {
    pops.value = pops.value.filter((p) => p.id !== popId)
  }, 500)
  room.send('pop', { id })
}

function loop(now: number): void {
  if (startLocal > 0 && !done.value) {
    timeLeft.value = Math.max(0, (durationMs - (now - startLocal)) / 1000)
    for (const m of motes.value) {
      const e = (now - m.start) / 1000
      m.x = m.x0 + m.vx * e
      m.y = 104 - m.vy * e
    }
    motes.value = motes.value.filter((m) => m.y > -8)
  }
  raf = requestAnimationFrame(loop)
}

function collect(): void {
  emit('finished', result.value)
}

onMounted(() => {
  raf = requestAnimationFrame(loop)
})
onUnmounted(() => cancelAnimationFrame(raf))
</script>

<style scoped>
.pollen__timer {
  position: relative;
  font-size: 15px;
  font-weight: 700;
  padding-bottom: 5px;
  min-width: 72px;
}
.pollen__timer--low {
  color: #ff7043;
}
.pollen__timer-bar {
  position: absolute;
  left: 0;
  bottom: 0;
  height: 3px;
  border-radius: 2px;
  background: currentColor;
  transition: width 0.3s linear;
  opacity: 0.7;
}
.pollen__score {
  font-size: 20px;
  font-weight: 800;
  font-variant-numeric: tabular-nums;
}
.pollen__arena {
  position: relative;
  /* Taps stay taps — don't let a touch-drag here pan/scroll the garden behind. */
  touch-action: none;
  width: 100%;
  height: 320px;
  border-radius: 16px;
  background:
    radial-gradient(ellipse 120% 60% at 50% 110%, rgba(126, 190, 80, 0.5), transparent 60%),
    linear-gradient(180deg, #aedcff 0%, #d8f0c8 70%, #b8dd90 100%);
  overflow: hidden;
  box-shadow: inset 0 4px 14px rgba(0, 0, 0, 0.12);
}
.pollen__mote {
  position: absolute;
  border: none;
  background: transparent;
  cursor: pointer;
  padding: 4px;
  line-height: 1;
  filter: drop-shadow(0 0 6px rgba(255, 235, 170, 0.8));
  transition: transform 0.08s;
}
.pollen__mote:active {
  transform: scale(1.7);
}
.pollen__pop {
  position: absolute;
  font-size: 14px;
  font-weight: 800;
  color: #2e7d32;
  pointer-events: none;
  animation: pop-float 0.5s ease-out forwards;
}
@keyframes pop-float {
  0% { transform: translate(-50%, 0) scale(1); opacity: 1; }
  100% { transform: translate(-50%, -26px) scale(1.4); opacity: 0; }
}
.pollen__overlay {
  position: absolute;
  inset: 0;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 4px;
  background: rgba(255, 255, 255, 0.86);
  color: #1b3a22;
}
.pollen__overlay-emoji {
  font-size: 42px;
}
</style>
