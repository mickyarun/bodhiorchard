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
-->
<!--
  Countdown to a target instant (all gating is server-side; this is cosmetic).
  variant="ring": a depleting ring that escalates green -> amber -> red and
  pulses near the deadline (needs `start` for the fraction). variant="text":
  a calm inline chip.
-->
<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref } from 'vue'

const props = withDefaults(
  defineProps<{
    target: string
    start?: string
    label?: string
    variant?: 'ring' | 'text'
  }>(),
  { variant: 'text' }
)

const now = ref(Date.now())
let timer: ReturnType<typeof setInterval> | null = null
onMounted(() => {
  timer = setInterval(() => (now.value = Date.now()), 1000)
})
onUnmounted(() => {
  if (timer) clearInterval(timer)
})

const remainingMs = computed(() => Math.max(0, new Date(props.target).getTime() - now.value))

const timeLabel = computed(() => {
  const s = Math.floor(remainingMs.value / 1000)
  if (s <= 0) return 'now'
  const h = Math.floor(s / 3600)
  const m = Math.floor((s % 3600) / 60)
  const sec = s % 60
  if (h > 0) return `${h}h ${m}m`
  if (m > 0) return `${m}:${String(sec).padStart(2, '0')}`
  return `${sec}s`
})

// Fraction of the window remaining (0..1), for the ring sweep.
const fraction = computed(() => {
  if (!props.start) return 1
  const startMs = new Date(props.start).getTime()
  const targetMs = new Date(props.target).getTime()
  const span = targetMs - startMs
  return span <= 0 ? 0 : Math.min(1, Math.max(0, remainingMs.value / span))
})

const urgency = computed<'low' | 'mid' | 'high'>(() => {
  if (remainingMs.value <= 60_000 || fraction.value < 0.15) return 'high'
  if (fraction.value < 0.4) return 'mid'
  return 'low'
})

// SVG ring geometry.
const R = 26
const C = 2 * Math.PI * R
const dashOffset = computed(() => C * (1 - fraction.value))
</script>

<template>
  <!-- Calm inline chip -->
  <div v-if="variant === 'text'" class="qc-text">
    <v-icon size="18" class="mr-1">mdi-timer-sand</v-icon>
    <span v-if="label" class="mr-1">{{ label }}</span>
    <strong>{{ timeLabel }}</strong>
  </div>

  <!-- Escalating ring -->
  <div v-else class="qc-ring" :class="`qc-ring--${urgency}`">
    <svg viewBox="0 0 64 64" class="qc-ring__svg" aria-hidden="true">
      <circle class="qc-ring__track" cx="32" cy="32" :r="R" fill="none" stroke-width="6" />
      <circle
        class="qc-ring__progress"
        cx="32"
        cy="32"
        :r="R"
        fill="none"
        stroke-width="6"
        stroke-linecap="round"
        :stroke-dasharray="C"
        :stroke-dashoffset="dashOffset"
        transform="rotate(-90 32 32)"
      />
    </svg>
    <div class="qc-ring__center">
      <span class="qc-ring__time">{{ timeLabel }}</span>
      <span v-if="label" class="qc-ring__label">{{ label }}</span>
    </div>
  </div>
</template>

<style scoped>
.qc-text {
  display: inline-flex;
  align-items: center;
  color: var(--color-muted);
  font-size: var(--text-sm);
}
.qc-text strong {
  color: var(--color-ink);
  font-variant-numeric: tabular-nums;
}

.qc-ring {
  position: relative;
  width: 84px;
  height: 84px;
  flex: 0 0 auto;
}
.qc-ring__svg {
  width: 100%;
  height: 100%;
}
.qc-ring__track {
  stroke: var(--color-rule);
}
.qc-ring__progress {
  transition:
    stroke-dashoffset 1s linear,
    stroke var(--dur-mid) var(--ease-out);
}
.qc-ring--low .qc-ring__progress {
  stroke: var(--color-accent);
}
.qc-ring--mid .qc-ring__progress {
  stroke: var(--color-warning);
}
.qc-ring--high .qc-ring__progress {
  stroke: var(--color-error);
}
.qc-ring__center {
  position: absolute;
  inset: 0;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  line-height: 1;
}
.qc-ring__time {
  font-weight: 800;
  font-size: 1.05rem;
  font-variant-numeric: tabular-nums;
  letter-spacing: -0.01em;
  color: var(--color-ink);
}
.qc-ring--high .qc-ring__time {
  color: var(--color-error);
}
.qc-ring__label {
  margin-top: 1px;
  font-size: 0.55rem;
  text-transform: uppercase;
  letter-spacing: 0.06em;
  color: var(--color-muted);
}
/* Escalate: pulse the whole ring as the deadline nears. */
.qc-ring--high {
  animation: qc-pulse 1s var(--ease-out) infinite;
}
@keyframes qc-pulse {
  0%,
  100% {
    transform: scale(1);
    opacity: 1;
  }
  50% {
    transform: scale(1.08);
    opacity: 0.85;
  }
}
@media (prefers-reduced-motion: reduce) {
  .qc-ring--high {
    animation: none;
  }
  .qc-ring__progress {
    transition: none;
  }
}
</style>
