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

  PollenPop — pop the drifting blossoms to clear each level's quota.

  Levels + lives: clear the pop quota to advance (each level spawns faster and
  rises faster); let too many blossoms escape and you lose a life. Out of lives
  ends the run. Each pop is a point.
-->
<template>
  <div class="pollen d-flex flex-column ga-2">
    <div class="d-flex align-center justify-space-between">
      <div class="pollen__hud">
        <span class="pollen__level">Lv {{ level }}</span>
        <span class="pollen__lives">
          <span
            v-for="n in POLLEN_LIVES"
            :key="n"
            class="pollen__heart"
            :class="{ 'pollen__heart--lost': n > lives }"
          >❤️</span>
        </span>
        <span
          class="pollen__missed"
          :class="{ 'pollen__missed--danger': escapes >= POLLEN_ESCAPE_BUDGET - 1 }"
          :title="`Let ${POLLEN_ESCAPE_BUDGET} flowers escape and you lose a heart`"
        >
          <span class="pollen__missed-label">missed</span>
          <span
            v-for="n in POLLEN_ESCAPE_BUDGET"
            :key="n"
            class="pollen__missed-pip"
            :class="{ 'pollen__missed-pip--lit': n <= escapes }"
          />
        </span>
      </div>
      <span class="pollen__score">{{ score }} <small>popped</small></span>
    </div>

    <div class="pollen__quota">
      <div class="pollen__quota-bar" :style="{ width: `${quotaPct}%` }" />
      <span class="pollen__quota-label">{{ popsInLevel }} / {{ quota }} to next level</span>
    </div>

    <div class="pollen__arena">
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

      <span
        v-for="f in escapeFlashes"
        :key="f.id"
        class="pollen__escape"
        :style="{ left: `${f.x}%` }"
      >🥀</span>

      <transition name="banner-pop">
        <div v-if="banner" :key="banner.id" class="pollen__banner" :class="`pollen__banner--${banner.kind}`">
          {{ banner.text }}
        </div>
      </transition>

      <div v-if="done" class="pollen__overlay">
        <span class="pollen__overlay-emoji">🌼</span>
        <div class="text-h6 font-weight-bold mb-1">Reached level {{ level }}</div>
        <div class="text-body-2 mb-2">{{ score }} blossoms popped</div>
        <v-btn color="success" rounded="lg" @click="collect">
          Collect points
        </v-btn>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref } from 'vue'
import { MOTE_EMOJI, POLLEN_ESCAPE_BUDGET, POLLEN_LIVES } from '@shared/minigames/pollen'
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
  flashed?: boolean // already flashed its escape as it left the top
}

const motes = ref<RenderMote[]>([])
const pops = ref<Array<{ id: number; x: number; y: number }>>([])
const escapeFlashes = ref<Array<{ id: number; x: number }>>([]) // red wilts at the top
const quota = ref(8) // pops needed to clear the current level
const popsInLevel = ref(0) // server-confirmed pops toward the current quota
const escapes = ref(0) // flowers missed this level (server count) — fills the meter
const banner = ref<{ id: number; text: string; kind: 'level' | 'life' } | null>(null)
const result = ref<MinigameResult | null>(null)

const room = useMinigameRoom('pollen_pop', { onEvent, onResult }, { startingLives: POLLEN_LIVES })
const score = room.score // authoritative count of valid pops
const level = computed(() => room.round.value || 1) // server level (state.round)
const lives = room.lives // authoritative lives remaining
const done = computed(() => room.status.value === 'finished')
const quotaPct = computed(() => Math.min(100, (popsInLevel.value / quota.value) * 100))

let raf = 0
let started = false
let popSeq = 1
let escapeSeq = 1
let bannerSeq = 1
let bannerTimer = 0

function showBanner(text: string, kind: 'level' | 'life'): void {
  banner.value = { id: bannerSeq++, text, kind }
  window.clearTimeout(bannerTimer)
  bannerTimer = window.setTimeout(() => {
    banner.value = null
  }, 1100)
}

function onEvent(type: string, payload: unknown): void {
  if (type === 'pollen_start') {
    quota.value = (payload as { quota: number }).quota
    popsInLevel.value = 0
    started = true
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
    // An escape: the server's running miss count drives the danger meter; the
    // red wilt itself is flashed client-side in loop() as the flower leaves.
    const p = payload as { id: number; escapes: number }
    escapes.value = p.escapes
    motes.value = motes.value.filter((m) => m.id !== p.id)
  } else if (type === 'pollen_popped') {
    const { id } = payload as { id: number }
    motes.value = motes.value.filter((m) => m.id !== id)
    popsInLevel.value += 1
  } else if (type === 'pollen_levelup') {
    quota.value = (payload as { quota: number }).quota
    popsInLevel.value = 0
    escapes.value = 0 // fresh miss meter each level
    showBanner(`⬆ Level ${(payload as { level: number }).level}!`, 'level')
  } else if (type === 'pollen_life') {
    escapes.value = 0 // budget blown → meter resets with the lost heart
    showBanner('💔 too many got away!', 'life')
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
  // Optimistic removal + feedback; the score (and quota progress) comes from
  // the server's pollen_popped, so a rejected pop doesn't advance the level.
  motes.value = motes.value.filter((mote) => mote.id !== id)
  const popId = popSeq++
  pops.value.push({ id: popId, x: m.x, y: m.y })
  window.setTimeout(() => {
    pops.value = pops.value.filter((p) => p.id !== popId)
  }, 500)
  room.send('pop', { id })
}

function loop(now: number): void {
  if (started && !done.value) {
    for (const m of motes.value) {
      const e = (now - m.start) / 1000
      m.x = m.x0 + m.vx * e
      m.y = 104 - m.vy * e
      // A flower slipping off the top unpopped = a miss. Flash a red wilt at the
      // edge so the player sees it (the meter count comes from the server).
      if (!m.flashed && m.y < 2) {
        m.flashed = true
        const fid = escapeSeq++
        escapeFlashes.value.push({ id: fid, x: m.x })
        window.setTimeout(() => {
          escapeFlashes.value = escapeFlashes.value.filter((f) => f.id !== fid)
        }, 650)
      }
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
onUnmounted(() => {
  cancelAnimationFrame(raf)
  window.clearTimeout(bannerTimer)
})
</script>

<style scoped>
.pollen__hud {
  display: flex;
  align-items: center;
  gap: 10px;
}
.pollen__level {
  font-size: 13px;
  font-weight: 800;
  padding: 2px 9px;
  border-radius: 999px;
  background: rgba(0, 0, 0, 0.12);
  letter-spacing: 0.03em;
}
.pollen__lives {
  display: flex;
  gap: 2px;
  font-size: 14px;
}
.pollen__heart--lost {
  opacity: 0.25;
  filter: grayscale(1);
}
.pollen__missed {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  padding-left: 4px;
}
.pollen__missed-label {
  font-size: 10px;
  font-weight: 700;
  text-transform: uppercase;
  letter-spacing: 0.04em;
  opacity: 0.55;
}
.pollen__missed-pip {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: rgba(0, 0, 0, 0.15);
  transition: background 0.15s;
}
.pollen__missed-pip--lit {
  background: #e05050;
}
.pollen__missed--danger .pollen__missed-label {
  opacity: 1;
  color: #d23b3b;
}
.pollen__missed--danger .pollen__missed-pip--lit {
  animation: missed-pulse 0.6s ease-in-out infinite;
}
@keyframes missed-pulse {
  0%, 100% { transform: scale(1); }
  50% { transform: scale(1.35); }
}
.pollen__escape {
  position: absolute;
  top: 0;
  font-size: 22px;
  transform: translate(-50%, 0);
  pointer-events: none;
  animation: escape-wilt 0.65s ease-out forwards;
}
@keyframes escape-wilt {
  0% { transform: translate(-50%, 6px) scale(1); opacity: 0; }
  25% { opacity: 1; }
  100% { transform: translate(-50%, -10px) scale(0.7); opacity: 0; }
}
.pollen__score {
  font-size: 20px;
  font-weight: 800;
  font-variant-numeric: tabular-nums;
}
.pollen__quota {
  position: relative;
  height: 16px;
  border-radius: 999px;
  background: rgba(0, 0, 0, 0.08);
  overflow: hidden;
}
.pollen__quota-bar {
  position: absolute;
  inset: 0 auto 0 0;
  background: linear-gradient(90deg, #7ec24f, #4ca64c);
  border-radius: 999px;
  transition: width 0.2s ease-out;
}
.pollen__quota-label {
  position: absolute;
  inset: 0;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 10px;
  font-weight: 700;
  letter-spacing: 0.03em;
  color: #1b3a22;
}
.pollen__arena {
  position: relative;
  /* Taps stay taps — don't let a touch-drag here pan/scroll the garden behind. */
  touch-action: none;
  width: 100%;
  height: 300px;
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
.pollen__banner {
  position: absolute;
  left: 50%;
  top: 24%;
  transform: translate(-50%, -50%);
  max-width: 90%;
  font-size: 18px;
  font-weight: 800;
  text-align: center;
  white-space: nowrap;
  padding: 8px 22px;
  border-radius: 999px;
  pointer-events: none;
  color: #fff;
}
.pollen__banner--level {
  background: rgba(76, 166, 76, 0.92);
}
.pollen__banner--life {
  background: rgba(229, 80, 80, 0.92);
}
.banner-pop-enter-active {
  animation: banner-in 0.3s ease-out;
}
@keyframes banner-in {
  0% { transform: translate(-50%, -30%) scale(0.6); opacity: 0; }
  100% { transform: translate(-50%, -50%) scale(1); opacity: 1; }
}
.pollen__overlay {
  position: absolute;
  inset: 0;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 2px;
  background: rgba(255, 255, 255, 0.86);
  color: #1b3a22;
}
.pollen__overlay-emoji {
  font-size: 42px;
}
</style>
