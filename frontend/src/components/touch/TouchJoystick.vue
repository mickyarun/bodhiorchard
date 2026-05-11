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

<!--
  TouchJoystick — floating thumbstick that maps finger position to
  WASD keydowns.

  Behaviour:
  - The joystick wrapper fills a bottom-left "zone" (pointer-events on
    the zone, pointer-events: none elsewhere). When the user touches
    anywhere in the zone, the visible base snaps to that point so the
    thumb starts under their finger — identical to Roblox's Dynamic
    Thumbstick and the "floating" mode in nipplejs.
  - While dragging, the thumb tracks the finger offset clamped to the
    base radius.
  - Movement is quantised per-axis against a deadzone: any time the X
    offset crosses ±threshold, KeyD / KeyA is pressed or released; same
    for Z against KeyS / KeyW. The per-axis approach feels natural
    because keyboards already allow W+D, W+A, etc. freely.
  - On pointerup/cancel all four keys are released.
-->

<template>
  <div
    class="touch-joystick"
    @pointerdown="onPointerDown"
    @pointermove="onPointerMove"
    @pointerup="onPointerUp"
    @pointercancel="onPointerUp"
  >
    <div
      v-if="active"
      class="touch-joystick__base"
      :style="{ left: baseX + 'px', top: baseY + 'px' }"
    >
      <div
        class="touch-joystick__thumb"
        :style="{ transform: `translate(calc(-50% + ${thumbDX}px), calc(-50% + ${thumbDY}px))` }"
      />
    </div>
    <div v-else class="touch-joystick__hint" aria-hidden="true">
      <div class="touch-joystick__hint-ring" />
    </div>
  </div>
</template>

<script setup lang="ts">
import { onBeforeUnmount, ref } from 'vue'
import { virtualKeyDown, virtualKeyUp } from '@/utils/virtualKeyboard'

const BASE_RADIUS = 70          // base visual radius (140px diameter)
const DEAD_ZONE = 0.18          // fraction of radius ignored before keys fire
const AXIS_THRESHOLD = 0.35     // fraction of radius at which WASD flips

const active = ref(false)
const baseX = ref(0)
const baseY = ref(0)
const thumbDX = ref(0)
const thumbDY = ref(0)
const activePointerId = ref<number | null>(null)

// Currently-held WASD keys — tracked so we only dispatch change events.
const held = { W: false, A: false, S: false, D: false }

function releaseAll(): void {
  if (held.W) { virtualKeyUp('KeyW'); held.W = false }
  if (held.A) { virtualKeyUp('KeyA'); held.A = false }
  if (held.S) { virtualKeyUp('KeyS'); held.S = false }
  if (held.D) { virtualKeyUp('KeyD'); held.D = false }
}

function applyAxes(dx: number, dy: number): void {
  // dx, dy are in pixels relative to base centre. Screen-Y is down, but
  // TakeoverController treats -Z as forward so moving the thumb up (dy
  // negative) must press W.
  const nx = dx / BASE_RADIUS
  const ny = dy / BASE_RADIUS
  const mag = Math.hypot(nx, ny)
  if (mag < DEAD_ZONE) { releaseAll(); return }

  const wantD = nx > AXIS_THRESHOLD
  const wantA = nx < -AXIS_THRESHOLD
  const wantS = ny > AXIS_THRESHOLD
  const wantW = ny < -AXIS_THRESHOLD

  if (wantW !== held.W) { wantW ? virtualKeyDown('KeyW') : virtualKeyUp('KeyW'); held.W = wantW }
  if (wantA !== held.A) { wantA ? virtualKeyDown('KeyA') : virtualKeyUp('KeyA'); held.A = wantA }
  if (wantS !== held.S) { wantS ? virtualKeyDown('KeyS') : virtualKeyUp('KeyS'); held.S = wantS }
  if (wantD !== held.D) { wantD ? virtualKeyDown('KeyD') : virtualKeyUp('KeyD'); held.D = wantD }
}

function onPointerDown(event: PointerEvent): void {
  if (activePointerId.value !== null) return
  event.preventDefault()
  const target = event.currentTarget as HTMLElement
  try { target.setPointerCapture(event.pointerId) } catch { /* some browsers disallow */ }
  activePointerId.value = event.pointerId

  const rect = target.getBoundingClientRect()
  baseX.value = event.clientX - rect.left
  baseY.value = event.clientY - rect.top
  thumbDX.value = 0
  thumbDY.value = 0
  active.value = true
}

function onPointerMove(event: PointerEvent): void {
  if (activePointerId.value !== event.pointerId) return
  const target = event.currentTarget as HTMLElement
  const rect = target.getBoundingClientRect()
  const localX = event.clientX - rect.left
  const localY = event.clientY - rect.top
  let dx = localX - baseX.value
  let dy = localY - baseY.value
  const mag = Math.hypot(dx, dy)
  if (mag > BASE_RADIUS) {
    dx = (dx / mag) * BASE_RADIUS
    dy = (dy / mag) * BASE_RADIUS
  }
  thumbDX.value = dx
  thumbDY.value = dy
  applyAxes(dx, dy)
}

function onPointerUp(event: PointerEvent): void {
  if (activePointerId.value !== event.pointerId) return
  activePointerId.value = null
  active.value = false
  thumbDX.value = 0
  thumbDY.value = 0
  releaseAll()
}

onBeforeUnmount(() => {
  // Guard against leaving keys held if the component unmounts mid-drag.
  releaseAll()
})
</script>

<style scoped>
.touch-joystick {
  position: absolute;
  left: 0;
  bottom: 0;
  width: 45%;
  max-width: 340px;
  height: 260px;
  pointer-events: auto;
  touch-action: none;
  -webkit-tap-highlight-color: transparent;
  user-select: none;
  -webkit-user-select: none;
}

.touch-joystick__base {
  position: absolute;
  width: 140px;
  height: 140px;
  border-radius: 50%;
  transform: translate(-50%, -50%);
  background: rgba(255, 255, 255, 0.08);
  border: 1px solid rgba(255, 255, 255, 0.22);
  backdrop-filter: blur(10px) saturate(140%);
  -webkit-backdrop-filter: blur(10px) saturate(140%);
  box-shadow:
    inset 0 1px 0 rgba(255, 255, 255, 0.18),
    0 4px 14px rgba(0, 0, 0, 0.2);
  pointer-events: none;
}

.touch-joystick__thumb {
  position: absolute;
  left: 50%;
  top: 50%;
  width: 60px;
  height: 60px;
  border-radius: 50%;
  background: rgba(255, 255, 255, 0.32);
  border: 1px solid rgba(255, 255, 255, 0.55);
  box-shadow:
    inset 0 1px 0 rgba(255, 255, 255, 0.22),
    0 2px 6px rgba(0, 0, 0, 0.22);
  pointer-events: none;
}

/* Idle hint — subtle ring at bottom-left suggesting the zone exists. */
.touch-joystick__hint {
  position: absolute;
  left: 80px;
  bottom: 80px;
  pointer-events: none;
  opacity: 0.45;
}
.touch-joystick__hint-ring {
  width: 120px;
  height: 120px;
  border-radius: 50%;
  border: 1px dashed rgba(255, 255, 255, 0.35);
  background: rgba(255, 255, 255, 0.06);
  backdrop-filter: blur(6px);
  -webkit-backdrop-filter: blur(6px);
}
</style>
