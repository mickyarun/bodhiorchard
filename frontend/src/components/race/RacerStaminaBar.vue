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

<!-- One racer's stamina bar. Renders a horizontal track with a colored
     fill whose width and hue map directly to staminaPct ∈ [0, 1]:
       > 0.6 → green   (safe to sprint)
       > 0.25 → amber  (consider pacing)
       else  → red     (one more burst will gas you out)
     Sized for the in-race HUD slot — kept thinner than the progress bar
     so the two never compete for attention. -->
<template>
  <div class="stamina-bar" :title="`Stamina: ${pctLabel}%`">
    <div
      class="stamina-bar__fill"
      :class="zoneClass"
      :style="{ width: clampedPct * 100 + '%' }"
    />
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'

interface Props {
  staminaPct: number
}

const props = defineProps<Props>()

const clampedPct = computed(() => {
  if (!Number.isFinite(props.staminaPct)) return 0
  return Math.max(0, Math.min(1, props.staminaPct))
})

const pctLabel = computed(() => Math.round(clampedPct.value * 100))

const zoneClass = computed(() => {
  if (clampedPct.value > 0.6) return 'stamina-bar__fill--ok'
  if (clampedPct.value > 0.25) return 'stamina-bar__fill--warn'
  return 'stamina-bar__fill--low'
})
</script>

<style scoped>
.stamina-bar {
  position: relative;
  height: 4px;
  border-radius: 2px;
  background: rgba(255, 255, 255, 0.08);
  overflow: hidden;
}
.stamina-bar__fill {
  height: 100%;
  border-radius: 2px;
  transition: width 0.15s linear, background 0.25s linear;
}
.stamina-bar__fill--ok {
  background: rgb(80, 200, 120);
}
.stamina-bar__fill--warn {
  background: rgb(240, 196, 76);
}
.stamina-bar__fill--low {
  background: rgb(232, 96, 88);
}
</style>
