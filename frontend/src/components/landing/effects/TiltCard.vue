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

<!-- 3D tilt that follows the cursor. Pointer handlers run only on devices with
     a fine pointer and when motion is allowed; touch + reduced-motion fall back
     to a static card. Modeled on the Inspira UI / Aceternity "3D / Tilt Card"
     pattern, implemented from scratch. -->
<template>
  <div
    ref="root"
    class="tilt-card"
    @pointermove="onMove"
    @pointerleave="onLeave"
  >
    <slot />
  </div>
</template>

<script setup lang="ts">
import { onMounted, ref } from 'vue'

const props = withDefaults(
  defineProps<{
    // Max tilt in degrees.
    max?: number
  }>(),
  { max: 7 },
)

const root = ref<HTMLElement | null>(null)
const enabled = ref(false)

onMounted(() => {
  const finePointer = window.matchMedia?.('(pointer: fine)').matches
  const prefersReduced = window.matchMedia?.('(prefers-reduced-motion: reduce)').matches
  enabled.value = !!finePointer && !prefersReduced
})

function onMove(e: PointerEvent): void {
  if (!enabled.value) return
  const el = root.value
  if (!el) return
  const rect = el.getBoundingClientRect()
  const px = (e.clientX - rect.left) / rect.width - 0.5
  const py = (e.clientY - rect.top) / rect.height - 0.5
  el.style.setProperty('--tilt-x', `${(-py * props.max).toFixed(2)}deg`)
  el.style.setProperty('--tilt-y', `${(px * props.max).toFixed(2)}deg`)
}

function onLeave(): void {
  const el = root.value
  if (!el) return
  el.style.setProperty('--tilt-x', '0deg')
  el.style.setProperty('--tilt-y', '0deg')
}
</script>

<style scoped>
.tilt-card {
  transform: perspective(900px) rotateX(var(--tilt-x, 0deg)) rotateY(var(--tilt-y, 0deg));
  transition: transform var(--dur-mid, 240ms) var(--ease-out, ease);
  transform-style: preserve-3d;
  will-change: transform;
}

@media (prefers-reduced-motion: reduce) {
  .tilt-card {
    transform: none;
    transition: none;
  }
}
</style>
