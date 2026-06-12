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

  FishingGame — timing-bar fishing at the forest lake.

  Five casts. A bobber sweeps across the bar; hook it inside the green
  strike zone. Closer to the zone's center = bigger fish = more points.
  Score: 0-50 (10 per perfect catch).
-->
<template>
  <div class="fishing-game d-flex flex-column align-center ga-4 pa-4">
    <div class="d-flex align-center ga-3 w-100 justify-space-between">
      <span class="text-subtitle-2">Cast {{ Math.min(cast + 1, CASTS) }} / {{ CASTS }}</span>
      <span class="text-subtitle-2">Score {{ score }}</span>
    </div>

    <!-- Timing bar -->
    <div class="fishing-game__bar" @pointerdown="hook">
      <div
        class="fishing-game__zone"
        :style="{ left: `${zoneStart * 100}%`, width: `${ZONE_WIDTH * 100}%` }"
      />
      <div class="fishing-game__bobber" :style="{ left: `${marker * 100}%` }">🎣</div>
    </div>

    <div class="text-caption text-medium-emphasis" style="min-height: 20px">
      {{ message }}
    </div>

    <v-btn
      v-if="!done"
      color="primary"
      size="large"
      block
      @pointerdown.stop="hook"
    >
      Hook! (or tap the bar)
    </v-btn>
    <v-btn v-else color="success" size="large" block @click="$emit('finished', score)">
      Done — collect {{ score }} points
    </v-btn>
  </div>
</template>

<script setup lang="ts">
import { onMounted, onUnmounted, ref } from 'vue'

defineEmits<{ finished: [score: number] }>()

const CASTS = 5
const ZONE_WIDTH = 0.16

const cast = ref(0)
const score = ref(0)
const marker = ref(0)
const zoneStart = ref(0.42)
const message = ref('Tap when the bobber is over the green water!')
const done = ref(false)

let raf = 0
let t = 0
let last = 0
let sweeping = true

function newZone(): void {
  zoneStart.value = 0.08 + Math.random() * (0.84 - ZONE_WIDTH)
}

function loop(now: number): void {
  if (last === 0) last = now
  const dt = (now - last) / 1000
  last = now
  if (sweeping) {
    // Sweep speeds up slightly with each cast
    t += dt * (0.9 + cast.value * 0.18)
    marker.value = (Math.sin(t * Math.PI) + 1) / 2
  }
  raf = requestAnimationFrame(loop)
}

function hook(): void {
  if (done.value || !sweeping) return
  sweeping = false
  const center = zoneStart.value + ZONE_WIDTH / 2
  const offset = Math.abs(marker.value - center) / (ZONE_WIDTH / 2)
  if (offset <= 1) {
    const points = offset < 0.35 ? 10 : offset < 0.7 ? 7 : 4
    score.value += points
    message.value = points === 10 ? 'Perfect catch! +10' : `Got one! +${points}`
  } else {
    message.value = 'It got away…'
  }
  cast.value += 1
  if (cast.value >= CASTS) {
    done.value = true
    message.value = `Final score: ${score.value}`
    return
  }
  window.setTimeout(() => {
    newZone()
    sweeping = true
  }, 700)
}

onMounted(() => {
  newZone()
  raf = requestAnimationFrame(loop)
})
onUnmounted(() => cancelAnimationFrame(raf))
</script>

<style scoped>
.fishing-game__bar {
  position: relative;
  width: 100%;
  height: 56px;
  border-radius: 12px;
  background: linear-gradient(180deg, #7ec8e3 0%, #4a9fc7 100%);
  overflow: hidden;
  cursor: pointer;
  user-select: none;
}
.fishing-game__zone {
  position: absolute;
  top: 0;
  height: 100%;
  background: rgba(80, 200, 120, 0.75);
  border-radius: 8px;
}
.fishing-game__bobber {
  position: absolute;
  top: 50%;
  transform: translate(-50%, -50%);
  font-size: 26px;
  pointer-events: none;
}
</style>
