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

  PollenPop — pop the drifting pollen motes before the clock runs out.

  25 seconds; motes rise through the play area; each pop is one point.
-->
<template>
  <div class="pollen-pop d-flex flex-column align-center ga-3 pa-4">
    <div class="d-flex align-center ga-3 w-100 justify-space-between">
      <span class="text-subtitle-2">⏱ {{ timeLeft.toFixed(0) }}s</span>
      <span class="text-subtitle-2">Popped {{ score }}</span>
    </div>

    <div ref="arena" class="pollen-pop__arena">
      <button
        v-for="m in motes"
        :key="m.id"
        class="pollen-pop__mote"
        :style="{ left: `${m.x}%`, top: `${m.y}%`, transform: `scale(${m.scale})` }"
        @pointerdown="pop(m.id)"
      >
        ✿
      </button>
      <div v-if="done" class="pollen-pop__overlay">
        <div class="text-h6 mb-2">Time! You popped {{ score }}</div>
        <v-btn color="success" @click="$emit('finished', score)">Collect points</v-btn>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { onMounted, onUnmounted, ref } from 'vue'

defineEmits<{ finished: [score: number] }>()

const GAME_SECONDS = 25
const SPAWN_EVERY_S = 0.55

interface Mote {
  id: number
  x: number   // percent
  y: number   // percent
  vy: number  // percent per second (upward)
  vx: number
  scale: number
}

const motes = ref<Mote[]>([])
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
    scale: 0.8 + Math.random() * 0.7,
  })
}

function pop(id: number): void {
  if (done.value) return
  const idx = motes.value.findIndex((m) => m.id === id)
  if (idx >= 0) {
    motes.value.splice(idx, 1)
    score.value += 1
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
.pollen-pop__arena {
  position: relative;
  width: 100%;
  height: 320px;
  border-radius: 12px;
  background: linear-gradient(180deg, #cfe9ff 0%, #e7f6dc 100%);
  overflow: hidden;
}
.pollen-pop__mote {
  position: absolute;
  border: none;
  background: transparent;
  font-size: 26px;
  color: #f0a832;
  cursor: pointer;
  transition: transform 0.1s;
  text-shadow: 0 0 8px rgba(255, 220, 130, 0.9);
}
.pollen-pop__mote:active {
  transform: scale(1.6) !important;
}
.pollen-pop__overlay {
  position: absolute;
  inset: 0;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  background: rgba(255, 255, 255, 0.82);
}
</style>
