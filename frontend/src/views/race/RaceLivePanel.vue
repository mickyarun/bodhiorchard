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

<template>
  <div class="race-live" :class="{ countdown: phase === 'countdown' }">
    <div ref="canvasHost" class="race-canvas" />

    <!-- Live HUD: timer + per-racer progress bars. Rendered during both
         countdown (0.0s timer) and running so racers see the field as soon
         as the scene mounts. Purely presentational — reads from the server
         snapshot directly. -->
    <div class="race-hud">
      <div class="race-hud__timer">
        <div class="race-hud__timer-value">{{ timerLabel }}</div>
        <div class="race-hud__timer-unit">s · {{ snapshot.distanceM }}m</div>
      </div>
      <ol class="race-hud__racers">
        <li
          v-for="r in racersByProgress"
          :key="r.userId"
          :class="{
            'race-hud__racer--self': r.userId === selfUserId,
            'race-hud__racer--finished': r.finished,
            'race-hud__racer--sprinting': isSprinting(r),
          }"
        >
          <span class="race-hud__rank">{{ r.finished ? placeFor(r.userId) : '·' }}</span>
          <span class="race-hud__name">{{ r.name }}</span>
          <div class="race-hud__bar">
            <div class="race-hud__bar-fill" :style="{ width: progressPct(r) + '%' }" />
          </div>
          <span class="race-hud__distance">{{ r.finished ? finishedLabel(r) : r.positionM.toFixed(0) + 'm' }}</span>
        </li>
      </ol>
    </div>

    <div v-if="phase === 'countdown'" class="countdown-overlay">
      <div class="countdown-value">{{ countdownLabel }}</div>
      <div class="countdown-hint">Hold your move key!</div>
    </div>

    <div v-if="isParticipant" class="controls-hint">
      Hold <kbd>W</kbd> or <kbd>↑</kbd> to move · tap <kbd>Shift</kbd> to sprint
    </div>

    <TouchControls
      v-if="isTouch && isParticipant && phase !== 'finished'"
      context="race"
    />
  </div>
</template>

<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { COUNTDOWN_MS } from '@shared/race/RaceConstants'
import { parseCharacterModel } from '@/engine/characters/CharacterConfig'
import { useAuthStore } from '@/stores/auth'
import { RaceEngine } from '@/engine/race'
import type { RacePhase } from '@shared/race/types'
import type { RaceRoomClientLike, RaceStateSnapshot } from '@/multiplayer/RaceRoomClient'
import TouchControls from '@/components/touch/TouchControls.vue'
import { useTouchDevice } from '@/composables/useTouchDevice'

const { isTouch } = useTouchDevice()

const props = defineProps<{
  snapshot: RaceStateSnapshot
  client: RaceRoomClientLike
  isParticipant: boolean
}>()

const authStore = useAuthStore()

const canvasHost = ref<HTMLElement | null>(null)
const engine = ref<RaceEngine | null>(null)
const countdownRemainingMs = ref(COUNTDOWN_MS)
const countdownTimer = ref<number | null>(null)

const phase = computed<RacePhase>(() => props.snapshot.phase)

const countdownLabel = computed(() => {
  const s = Math.ceil(countdownRemainingMs.value / 1000)
  return s > 0 ? String(s) : 'GO!'
})

const selfUserId = computed(() => authStore.user?.id ?? '')

const timerLabel = computed(() => (props.snapshot.runningElapsedMs / 1000).toFixed(1))

/** Racers ordered by current progress, finishers pinned to the top by place. */
const racersByProgress = computed(() => {
  const list = [...props.snapshot.racers]
  list.sort((a, b) => {
    if (a.finished && b.finished) return a.finishTimeMs - b.finishTimeMs
    if (a.finished !== b.finished) return a.finished ? -1 : 1
    return b.positionM - a.positionM
  })
  return list
})

function progressPct(r: { positionM: number }): number {
  const d = props.snapshot.distanceM || 1
  return Math.max(0, Math.min(1, r.positionM / d)) * 100
}

function isSprinting(r: { sprintUntilMs: number }): boolean {
  return props.snapshot.runningElapsedMs < r.sprintUntilMs
}

function placeFor(userId: string): string {
  const p = props.snapshot.placings.find(x => x.racerId === userId)
  return p ? `#${p.place}` : '·'
}

function finishedLabel(r: { userId: string; finishTimeMs: number }): string {
  return (r.finishTimeMs / 1000).toFixed(2) + 's'
}

onMounted(async () => {
  if (!canvasHost.value) return
  const built = await buildEngine()
  if (!built) return
  installKeyHandlers()
  startCountdownTimer()
})

onBeforeUnmount(() => {
  if (countdownTimer.value !== null) window.clearInterval(countdownTimer.value)
  removeKeyHandlers()
  engine.value?.destroy()
  engine.value = null
})

// Mirror server racer kinematics onto the scene every snapshot update.
// We also remember each racer's finished flag so we only call setRacerFinished
// on the edge (false → true), which keeps the Cheer emote from being
// re-triggered every 50 ms while the placings panel is visible.
const finishedSeen = new Set<string>()
watch(
  () => props.snapshot.racers,
  (racers) => {
    const eng = engine.value
    if (!eng) return
    for (const r of racers) {
      const sprinting = props.snapshot.runningElapsedMs < r.sprintUntilMs
      eng.setRacerKinematics(r.userId, r.positionM, r.velocityMps, sprinting)
      if (r.finished && !finishedSeen.has(r.userId)) {
        finishedSeen.add(r.userId)
        eng.setRacerFinished(r.userId, true)
      }
    }
  },
  { deep: true },
)

async function buildEngine(): Promise<boolean> {
  if (!canvasHost.value) return false
  const instance = new RaceEngine()
  const racers = props.snapshot.racers.map((r, idx) => ({
    id: r.userId,
    name: r.name,
    laneIndex: r.laneIndex ?? idx,
    config: parseCharacterModel(r.characterModel),
  }))
  try {
    await instance.init(canvasHost.value, {
      width: canvasHost.value.clientWidth,
      height: canvasHost.value.clientHeight,
      scene: {
        distanceM: props.snapshot.distanceM,
        racerCount: racers.length,
        cameraMode: props.isParticipant ? 'participant' : 'spectator',
        racers,
        // Participants see their own avatar — camera sticks to the current
        // user's racer id, not whoever is furthest forward. Spectators fall
        // through to the overhead camera (ignores leaderProvider).
        leaderProvider: () => {
          const selfId = authStore.user?.id ?? ''
          if (selfId && instance) return instance.getRacerDisplayX(selfId)
          return 0
        },
      },
    })
    engine.value = instance
    return true
  } catch (err) {
    console.error('[RaceLivePanel] engine init failed:', err)
    instance.destroy()
    return false
  }
}

function startCountdownTimer(): void {
  const refresh = (): void => {
    if (props.snapshot.phase !== 'countdown') {
      countdownRemainingMs.value = 0
      return
    }
    const elapsed = Date.now() - props.snapshot.phaseStartMs
    countdownRemainingMs.value = Math.max(0, COUNTDOWN_MS - elapsed)
  }
  refresh()
  countdownTimer.value = window.setInterval(refresh, 100)
}

// ─── participant input ─────────────────────

let isMoveKeyDown = false

function onKeyDown(ev: KeyboardEvent): void {
  if (!props.isParticipant) return
  if (isMoveKey(ev)) {
    if (!isMoveKeyDown) {
      isMoveKeyDown = true
      props.client.sendMove(true)
    }
  } else if (isSprintKey(ev)) {
    // Tap-to-sprint — each keydown counts as a tap, including auto-repeat.
    props.client.sendSprintTap()
  }
}

function onKeyUp(ev: KeyboardEvent): void {
  if (!props.isParticipant) return
  if (isMoveKey(ev)) {
    if (isMoveKeyDown) {
      isMoveKeyDown = false
      props.client.sendMove(false)
    }
  }
}

function isMoveKey(ev: KeyboardEvent): boolean {
  return ev.key === 'w' || ev.key === 'W' || ev.key === 'ArrowUp'
}

function isSprintKey(ev: KeyboardEvent): boolean {
  return ev.key === 'Shift' || ev.code === 'ShiftLeft' || ev.code === 'ShiftRight'
}

function installKeyHandlers(): void {
  window.addEventListener('keydown', onKeyDown)
  window.addEventListener('keyup', onKeyUp)
}

function removeKeyHandlers(): void {
  window.removeEventListener('keydown', onKeyDown)
  window.removeEventListener('keyup', onKeyUp)
}
</script>

<style scoped>
.race-live {
  position: relative;
  width: 100%;
  height: 100%;
  overflow: hidden;
  font-family: system-ui, -apple-system, sans-serif;
}
.race-canvas {
  width: 100%;
  height: 100%;
}

/* ── Live HUD ─────────────────────────────── */
.race-hud {
  position: absolute;
  top: 20px;
  left: 20px;
  min-width: 340px;
  max-width: 420px;
  background: linear-gradient(180deg, rgba(12, 18, 32, 0.82), rgba(12, 18, 32, 0.7));
  border: 1px solid rgba(255, 255, 255, 0.08);
  border-radius: 14px;
  padding: 14px 18px 12px;
  color: #fff;
  backdrop-filter: blur(8px);
  box-shadow: 0 10px 28px rgba(0, 0, 0, 0.3);
  pointer-events: none;
}
.race-hud__timer {
  display: flex;
  align-items: baseline;
  gap: 8px;
  margin-bottom: 10px;
  padding-bottom: 10px;
  border-bottom: 1px solid rgba(255, 255, 255, 0.08);
}
.race-hud__timer-value {
  font-size: 34px;
  font-weight: 800;
  font-variant-numeric: tabular-nums;
  letter-spacing: -0.02em;
  line-height: 1;
}
.race-hud__timer-unit {
  font-size: 12px;
  text-transform: uppercase;
  letter-spacing: 0.08em;
  color: rgba(255, 255, 255, 0.6);
}
.race-hud__racers {
  list-style: none;
  margin: 0;
  padding: 0;
  display: flex;
  flex-direction: column;
  gap: 4px;
}
.race-hud__racers li {
  display: grid;
  grid-template-columns: 28px 1fr 80px;
  grid-template-rows: auto auto;
  column-gap: 10px;
  align-items: center;
  padding: 6px 8px;
  border-radius: 8px;
  transition: background 0.2s;
}
.race-hud__racers li.race-hud__racer--self {
  background: rgba(120, 180, 255, 0.12);
  outline: 1px solid rgba(120, 180, 255, 0.22);
}
.race-hud__racers li.race-hud__racer--sprinting .race-hud__bar-fill {
  background: linear-gradient(90deg, #ffd75e, #ff6b4a);
}
.race-hud__racers li.race-hud__racer--finished {
  background: rgba(80, 200, 120, 0.12);
}
.race-hud__rank {
  grid-row: span 2;
  font-weight: 700;
  font-variant-numeric: tabular-nums;
  text-align: center;
  color: rgba(255, 255, 255, 0.75);
  font-size: 13px;
}
.race-hud__racer--finished .race-hud__rank {
  color: #ffd75e;
}
.race-hud__name {
  font-weight: 600;
  font-size: 13px;
  overflow: hidden;
  white-space: nowrap;
  text-overflow: ellipsis;
}
.race-hud__distance {
  text-align: right;
  font-variant-numeric: tabular-nums;
  font-size: 12px;
  color: rgba(255, 255, 255, 0.7);
}
.race-hud__bar {
  grid-column: 2 / 3;
  height: 6px;
  border-radius: 3px;
  background: rgba(255, 255, 255, 0.1);
  overflow: hidden;
}
.race-hud__bar-fill {
  height: 100%;
  background: linear-gradient(90deg, #7cc9ff, #4f8cff);
  transition: width 0.1s linear;
}

/* ── Countdown overlay ────────────────────── */
.countdown-overlay {
  position: absolute;
  inset: 0;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  pointer-events: none;
  color: #fff;
}
.countdown-value {
  font-size: 200px;
  font-weight: 900;
  line-height: 1;
  letter-spacing: -0.05em;
  text-shadow: 0 6px 30px rgba(0, 0, 0, 0.55), 0 0 60px rgba(255, 215, 94, 0.25);
  animation: countdown-pop 1s ease-out;
}
.countdown-hint {
  margin-top: 12px;
  font-size: 15px;
  opacity: 0.85;
  text-shadow: 0 2px 8px rgba(0, 0, 0, 0.6);
}
@keyframes countdown-pop {
  0%   { transform: scale(1.4); opacity: 0; }
  30%  { transform: scale(1);   opacity: 1; }
  100% { transform: scale(1);   opacity: 1; }
}

/* ── Controls hint ────────────────────────── */
.controls-hint {
  position: absolute;
  bottom: 22px;
  left: 50%;
  transform: translateX(-50%);
  color: #fff;
  background: rgba(12, 18, 32, 0.7);
  border: 1px solid rgba(255, 255, 255, 0.08);
  padding: 8px 16px;
  border-radius: 999px;
  font-size: 13px;
  backdrop-filter: blur(8px);
}
.controls-hint kbd {
  background: rgba(255, 255, 255, 0.14);
  padding: 2px 7px;
  border-radius: 5px;
  font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
  font-size: 12px;
  margin: 0 2px;
  border: 1px solid rgba(255, 255, 255, 0.08);
  box-shadow: 0 1px 0 rgba(0, 0, 0, 0.3) inset;
}
</style>
