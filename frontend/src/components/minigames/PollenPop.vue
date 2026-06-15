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
        <v-btn color="success" rounded="lg" @click="$emit('finished', score)">
          Collect points
        </v-btn>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { onMounted, onUnmounted, ref } from 'vue'

defineEmits<{ finished: [score: number] }>()

const GAME_SECONDS = 25
const SPAWN_EVERY_S = 0.55
const MOTE_EMOJI = ['🌸', '🌼', '💮', '🌺']

interface Mote {
  id: number
  x: number   // percent
  y: number   // percent
  vy: number  // percent per second (upward)
  vx: number
  scale: number
  emoji: string
}

const motes = ref<Mote[]>([])
const pops = ref<Array<{ id: number; x: number; y: number }>>([])
const score = ref(0)
const timeLeft = ref(GAME_SECONDS)
const done = ref(false)
const arena = ref<HTMLElement | null>(null)

let raf = 0
let last = 0
let spawnAcc = 0
let nextId = 1

function spawn(): void {
  motes.value.push({
    id: nextId++,
    x: 8 + Math.random() * 84,
    y: 104,
    vy: 9 + Math.random() * 10,
    vx: (Math.random() - 0.5) * 6,
    scale: 0.8 + Math.random() * 0.8,
    emoji: MOTE_EMOJI[Math.floor(Math.random() * MOTE_EMOJI.length)],
  })
}

function pop(id: number, _ev: PointerEvent): void {
  if (done.value) return
  const idx = motes.value.findIndex((m) => m.id === id)
  if (idx >= 0) {
    const m = motes.value[idx]
    motes.value.splice(idx, 1)
    score.value += 1
    const popId = nextId++
    pops.value.push({ id: popId, x: m.x, y: m.y })
    window.setTimeout(() => {
      pops.value = pops.value.filter((p) => p.id !== popId)
    }, 500)
  }
}

function loop(now: number): void {
  if (last === 0) last = now
  const dt = Math.min((now - last) / 1000, 0.1)
  last = now

  if (!done.value) {
    timeLeft.value = Math.max(0, timeLeft.value - dt)
    if (timeLeft.value <= 0) {
      done.value = true
      motes.value = []
    }

    spawnAcc += dt
    while (spawnAcc >= SPAWN_EVERY_S) {
      spawnAcc -= SPAWN_EVERY_S
      spawn()
    }

    for (const m of motes.value) {
      m.y -= m.vy * dt
      m.x += m.vx * dt
    }
    motes.value = motes.value.filter((m) => m.y > -8)
  }

  raf = requestAnimationFrame(loop)
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
