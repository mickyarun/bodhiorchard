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

<!-- Card whose accent spotlight follows the cursor. Pointer math runs only
     after mount (SSR-safe); the static card renders fine without JS. Modeled
     on the Inspira UI / Aceternity "Spotlight Card" pattern, implemented from
     scratch with CSS custom properties. -->
<template>
  <div
    ref="root"
    class="spotlight-card card-border-dark"
    @pointermove="onMove"
    @pointerleave="onLeave"
  >
    <div class="spotlight-card__glow" aria-hidden="true" />
    <div class="spotlight-card__content">
      <slot />
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref } from 'vue'

const root = ref<HTMLElement | null>(null)

function onMove(e: PointerEvent): void {
  const el = root.value
  if (!el) return
  const rect = el.getBoundingClientRect()
  el.style.setProperty('--spot-x', `${e.clientX - rect.left}px`)
  el.style.setProperty('--spot-y', `${e.clientY - rect.top}px`)
  el.style.setProperty('--spot-opacity', '1')
}

function onLeave(): void {
  root.value?.style.setProperty('--spot-opacity', '0')
}
</script>

<style scoped>
.spotlight-card {
  position: relative;
  overflow: hidden;
  border-radius: var(--radius-card, 10px);
  background: rgb(var(--v-theme-surface));
  transition: transform var(--dur-mid, 240ms) var(--ease-out, ease), border-color var(--dur-mid, 240ms) var(--ease-out, ease);
}
.spotlight-card:hover {
  transform: translateY(-3px);
  border-color: rgba(var(--v-theme-primary), 0.35) !important;
}
.spotlight-card__glow {
  position: absolute;
  inset: 0;
  pointer-events: none;
  opacity: var(--spot-opacity, 0);
  transition: opacity var(--dur-mid, 240ms) var(--ease-out, ease);
  background: radial-gradient(
    240px circle at var(--spot-x, 50%) var(--spot-y, 0),
    rgba(var(--v-theme-primary), 0.16),
    transparent 60%
  );
}
.spotlight-card__content {
  position: relative;
  z-index: 1;
}

@media (prefers-reduced-motion: reduce) {
  .spotlight-card,
  .spotlight-card__glow {
    transition: none;
  }
  .spotlight-card:hover {
    transform: none;
  }
}
</style>
