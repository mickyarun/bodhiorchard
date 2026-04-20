<!-- SPDX-License-Identifier: AGPL-3.0-or-later -->
<!-- Copyright (C) 2026 Arun Rajkumar -->
<template>
  <div class="results">
    <RaceThemeBackdrop />
    <div class="results__confetti" aria-hidden="true">
      <span v-for="i in 24" :key="i" class="results__confetti-piece" :style="confettiStyle(i)" />
    </div>

    <header class="results__header">
      <div class="results__eyebrow">
        <CheckerFlagIcon />
        {{ snapshot.distanceM }} m sprint · final standings
      </div>
      <h1 class="results__title">Race complete</h1>
    </header>

    <v-alert v-if="rematchError" type="error" class="mb-4" density="compact">
      {{ rematchError }}
    </v-alert>

    <!-- Podium — top 3 finishers rendered as 3D characters on a tiered stage.
         Winner in the centre playing the Cheer emote; runners-up flank the
         sides with idle (a "watching the winner" pose rather than explicit
         sadness, which reads poorly for a short sprint). Fallback: if
         there's only a winner, render them solo without empty podium spots. -->
    <div class="results__podium" v-if="podiumSlots.length > 0">
      <div
        v-for="spot in podiumSlots"
        :key="spot.key"
        class="podium-spot"
        :class="`podium-spot--place-${spot.place}`"
        :style="{ order: spot.visualOrder }"
      >
        <div class="podium-spot__spotlight" aria-hidden="true" />
        <div class="podium-spot__preview">
          <CharacterPreview :config="spot.config" :emote="spot.emote" class="podium-spot__canvas" />
        </div>
        <div class="podium-spot__plinth">
          <span class="podium-spot__medal">
            <v-icon v-if="spot.place === 1" icon="mdi-trophy" size="22" />
            <span v-else>{{ spot.place }}</span>
          </span>
          <span class="podium-spot__name">{{ spot.name }}</span>
          <span class="podium-spot__time">{{ spot.timeLabel }}</span>
        </div>
      </div>
    </div>

    <!-- Ranking list for anyone past 3rd (and for races with fewer than 3
         finishers that don't need a full podium). Renders compactly so
         a full 10-racer field still fits without dominating the layout. -->
    <ol v-if="listRows.length" class="results__list">
      <li
        v-for="row in listRows"
        :key="row.racerId"
        :class="['results__row', { 'results__row--dnf': !row.finished }]"
      >
        <span class="results__place">{{ row.finished ? row.place : 'DNF' }}</span>
        <span class="results__avatar">{{ initialsOf(row.racerId) }}</span>
        <span class="results__name">{{ nameOf(row.racerId) }}</span>
        <span class="results__time">
          {{ row.finished ? formatRaceTime(row.finishTimeMs) : `${row.distanceM.toFixed(1)}m` }}
        </span>
      </li>
    </ol>

    <div class="results__actions">
      <button class="results__back" @click="$emit('leave')">
        <v-icon icon="mdi-arrow-left" size="18" class="mr-1" />
        Back to garden
      </button>
      <button
        v-if="isHost"
        class="results__rematch"
        :disabled="rematchLoading"
        @click="onRematch"
      >
        <v-progress-circular v-if="rematchLoading" indeterminate size="18" width="2" color="white" class="mr-1" />
        <v-icon v-else icon="mdi-refresh" size="18" class="mr-1" />
        Rematch
      </button>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, ref } from 'vue'
import { useRouter } from 'vue-router'
import { useAuthStore } from '@/stores/auth'
import { OrgRoomClient } from '@/multiplayer/OrgRoomClient'
import type { RaceStateSnapshot } from '@/multiplayer/RaceRoomClient'
import { formatRaceTime } from '@/engine/race/formatTime'
import { parseCharacterModel, type CharacterConfig } from '@/engine/characters/CharacterConfig'
import CharacterPreview from '@/components/character/CharacterPreview.vue'
import RaceThemeBackdrop from '@/components/race/RaceThemeBackdrop.vue'
import CheckerFlagIcon from '@/components/race/CheckerFlagIcon.vue'
import { initials } from '@/components/race/initials'

const props = defineProps<{
  snapshot: RaceStateSnapshot
}>()

defineEmits<{
  (e: 'leave'): void
}>()

const router = useRouter()
const authStore = useAuthStore()
const rematchLoading = ref(false)
const rematchError = ref<string>('')

const rows = computed(() => props.snapshot.placings)

const isHost = computed(
  () => !!authStore.user && authStore.user.id === props.snapshot.hostUserId,
)

const nameByUserId = computed(() => {
  const m = new Map<string, string>()
  for (const r of props.snapshot.racers) m.set(r.userId, r.name)
  return m
})

const configByUserId = computed(() => {
  const m = new Map<string, CharacterConfig>()
  for (const r of props.snapshot.racers) {
    m.set(r.userId, parseCharacterModel(r.characterModel))
  }
  return m
})

function nameOf(userId: string): string {
  return nameByUserId.value.get(userId) ?? userId
}

function initialsOf(userId: string): string {
  return initials(nameOf(userId))
}

function configOf(userId: string): CharacterConfig {
  return configByUserId.value.get(userId) ?? parseCharacterModel('')
}

/**
 * Top 3 placings mapped to podium spots. `visualOrder` re-arranges so the
 * winner appears centre (order 2) with 2nd on the left (order 1) and 3rd
 * on the right (order 3) — mirrors real-world Olympic-style podiums.
 */
interface PodiumSpot {
  key: string
  place: number
  name: string
  config: CharacterConfig
  emote: 0 | 2 | 3
  timeLabel: string
  /** CSS `order` value — lower = leftmost. */
  visualOrder: number
}

const podiumSlots = computed<PodiumSpot[]>(() => {
  const top = rows.value.filter(r => r.finished).slice(0, 3)
  return top.map(r => ({
    key: r.racerId,
    place: r.place,
    name: nameOf(r.racerId),
    config: configOf(r.racerId),
    // Winner cheers (emote=2); everyone else plays the defeat animation
    // (emote=3 → KayKit's `Death_A` track, slowed to 0.6× in the state
    // graph so the "knocked over" keyframes read as "dejected" rather
    // than "bled out in combat").
    emote: r.place === 1 ? 2 : 3,
    timeLabel: formatRaceTime(r.finishTimeMs),
    // Visual: 2nd at order=1 (left), 1st at order=2 (centre), 3rd at order=3 (right).
    visualOrder: r.place === 1 ? 2 : r.place === 2 ? 1 : 3,
  }))
})

/** Placings past the podium — shown as a compact list below. */
const listRows = computed(() =>
  rows.value.filter(r => r.place > 3 || !r.finished),
)

/** Seeded-ish style values so confetti pieces stay stable across re-renders. */
function confettiStyle(i: number): Record<string, string> {
  // Simple hash for determinism — no side-effects, no animation jitter.
  const seed = Math.sin(i * 7.13) * 1000
  const left = Math.abs(seed % 100)
  const delay = (Math.abs(seed * 3) % 6).toFixed(1)
  const duration = (3 + Math.abs(seed * 5) % 3).toFixed(1)
  const colors = ['#ffd75e', '#30d66d', '#7cc9ff', '#ff6b4a', '#a374ff']
  const color = colors[i % colors.length]
  const rotate = Math.abs(seed * 2) % 360
  return {
    left: `${left}%`,
    animationDelay: `${delay}s`,
    animationDuration: `${duration}s`,
    background: color,
    transform: `rotate(${rotate}deg)`,
  }
}

async function onRematch(): Promise<void> {
  if (!isHost.value || rematchLoading.value) return
  const invitedUserIds = props.snapshot.invitedUserIds
  if (invitedUserIds.length === 0) {
    rematchError.value = 'Rematch needs at least one invitee.'
    return
  }
  rematchLoading.value = true
  rematchError.value = ''
  try {
    const client = OrgRoomClient.getInstance()
    const { roomId } = await client.sendRaceCreate({
      invitedUserIds: [...invitedUserIds],
      distanceM: props.snapshot.distanceM,
    })
    await router.push(`/raceview/${roomId}`)
  } catch (err) {
    console.error('[RaceResultsCard] rematch failed:', err)
    rematchError.value = err instanceof Error ? err.message : 'Rematch failed.'
  } finally {
    rematchLoading.value = false
  }
}
</script>

<style scoped>
.results {
  position: relative;
  min-height: 100%;
  padding: 32px 24px 40px;
  color: #fff;
  font-family: system-ui, -apple-system, 'Segoe UI', sans-serif;
  isolation: isolate;
  /* x-hidden keeps the diagonal stripe overflow clipped sideways; y-auto
     lets the page scroll when 4th–10th place rows push content past the
     viewport. Without this, overflow:hidden was clipping the tail list
     at max density (10 racers). */
  overflow-x: hidden;
  overflow-y: auto;
}

/* Confetti — small coloured chips falling from the top. Pure CSS.
   The stripe/glow backdrop is provided by <RaceThemeBackdrop />. */
.results__confetti {
  position: absolute;
  inset: 0;
  overflow: hidden;
  z-index: 0;
  pointer-events: none;
}
.results__confetti-piece {
  position: absolute;
  top: -20px;
  width: 8px;
  height: 14px;
  border-radius: 2px;
  opacity: 0.9;
  animation-name: confetti-fall;
  animation-timing-function: linear;
  animation-iteration-count: infinite;
}
@keyframes confetti-fall {
  0%   { transform: translateY(-20px) rotate(0deg);    opacity: 0; }
  10%  { opacity: 1; }
  80%  { opacity: 1; }
  100% { transform: translateY(100vh) rotate(720deg);  opacity: 0; }
}

.results > *:not(.race-theme-backdrop):not(.results__confetti) {
  position: relative;
  z-index: 1;
  max-width: 980px;
  margin-left: auto;
  margin-right: auto;
}

/* ── Header ──────────────────────────────── */
.results__header {
  text-align: center;
  margin-bottom: 28px;
}
.results__eyebrow {
  display: inline-flex;
  align-items: center;
  gap: 10px;
  text-transform: uppercase;
  letter-spacing: 0.2em;
  font-size: 12px;
  font-weight: 600;
  color: rgba(255, 255, 255, 0.7);
  padding: 6px 14px;
  border-radius: 999px;
  background: rgba(255, 255, 255, 0.04);
  border: 1px solid rgba(255, 255, 255, 0.08);
  margin-bottom: 10px;
}
.results__title {
  font-size: clamp(38px, 6vw, 56px);
  font-weight: 900;
  margin: 0;
  letter-spacing: -0.02em;
  font-style: italic;
  line-height: 1;
  text-shadow: 0 6px 30px rgba(0, 0, 0, 0.4);
  background: linear-gradient(180deg, #fff 0%, #ffd75e 100%);
  -webkit-background-clip: text;
  background-clip: text;
  -webkit-text-fill-color: transparent;
}

/* ── Podium ───────────────────────────────── */
.results__podium {
  display: flex;
  justify-content: center;
  align-items: stretch;   /* stretch so every card spans the same height */
  gap: 18px;
  margin: 24px 0 24px;
  flex-wrap: wrap;
}

.podium-spot {
  position: relative;
  display: flex;
  flex-direction: column;
  align-items: stretch;
  width: clamp(200px, 28vw, 240px);
  transition: transform 0.3s ease;
}
/* Winner isn't made taller (height mismatches looked ragged at narrow
   widths and the trophy/confetti do the heavy lifting for hierarchy).
   Instead the winner gets a stronger border + amber glow. */
.podium-spot--place-1 .podium-spot__preview {
  border-color: rgba(255, 215, 94, 0.55);
  box-shadow:
    0 18px 45px rgba(255, 152, 0, 0.35),
    0 0 0 1px rgba(255, 215, 94, 0.35) inset,
    0 0 80px rgba(255, 193, 7, 0.18);
}
.podium-spot--place-2 .podium-spot__preview {
  border-color: rgba(200, 200, 200, 0.4);
  box-shadow: 0 14px 34px rgba(0, 0, 0, 0.4);
}
.podium-spot--place-3 .podium-spot__preview {
  border-color: rgba(205, 127, 50, 0.4);
  box-shadow: 0 14px 34px rgba(0, 0, 0, 0.4);
}

.podium-spot__spotlight {
  position: absolute;
  top: -40px;
  left: 50%;
  transform: translateX(-50%);
  width: 120%;
  height: 50%;
  background: radial-gradient(ellipse, rgba(255, 215, 94, 0.18), transparent 70%);
  filter: blur(30px);
  pointer-events: none;
}
.podium-spot--place-1 .podium-spot__spotlight {
  background: radial-gradient(ellipse, rgba(255, 215, 94, 0.35), transparent 70%);
}

.podium-spot__preview {
  position: relative;
  width: 100%;
  aspect-ratio: 4 / 5;       /* same on every card so the three tiles line up */
  flex: 1 0 auto;            /* fills any extra vertical space inside the spot */
  border-radius: 18px 18px 0 0;
  overflow: hidden;
  border: 1px solid rgba(255, 255, 255, 0.1);
  background:
    radial-gradient(ellipse at 50% 75%, rgba(100, 140, 200, 0.22), transparent 60%),
    linear-gradient(180deg, #0f1728 0%, #080c16 100%);
}
.podium-spot__canvas,
.podium-spot__canvas :deep(.character-preview) {
  width: 100%;
  height: 100%;
  min-height: 0 !important;
  background: transparent;
}

.podium-spot__plinth {
  width: 100%;
  display: grid;
  grid-template-columns: auto 1fr auto;
  gap: 10px;
  align-items: center;
  padding: 14px 16px;
  border-radius: 0 0 16px 16px;
  background: linear-gradient(180deg, rgba(18, 26, 40, 0.9), rgba(12, 18, 30, 0.85));
  border: 1px solid rgba(255, 255, 255, 0.08);
  border-top: none;
}
.podium-spot--place-1 .podium-spot__plinth {
  background: linear-gradient(180deg, rgba(90, 62, 20, 0.85), rgba(60, 38, 8, 0.85));
  border-color: rgba(255, 215, 94, 0.35);
}
.podium-spot--place-2 .podium-spot__plinth {
  background: linear-gradient(180deg, rgba(60, 65, 72, 0.85), rgba(42, 48, 55, 0.85));
  border-color: rgba(200, 200, 200, 0.22);
}
.podium-spot--place-3 .podium-spot__plinth {
  background: linear-gradient(180deg, rgba(70, 45, 28, 0.85), rgba(52, 32, 18, 0.85));
  border-color: rgba(205, 127, 50, 0.22);
}

.podium-spot__medal {
  width: 36px;
  height: 36px;
  border-radius: 50%;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  font-weight: 900;
  font-size: 15px;
  background: rgba(255, 255, 255, 0.08);
  color: #fff;
}
.podium-spot--place-1 .podium-spot__medal {
  background: linear-gradient(135deg, #ffd75e, #ff9500);
  color: #2a1a00;
  box-shadow: 0 4px 12px rgba(255, 149, 0, 0.4);
}
.podium-spot--place-2 .podium-spot__medal {
  background: linear-gradient(135deg, #e5e5e5, #9a9a9a);
  color: #1a1a1a;
}
.podium-spot--place-3 .podium-spot__medal {
  background: linear-gradient(135deg, #d59864, #8b5a2b);
  color: #1a1a1a;
}

.podium-spot__name {
  font-weight: 700;
  font-size: 15px;
  overflow: hidden;
  white-space: nowrap;
  text-overflow: ellipsis;
  letter-spacing: -0.01em;
}
.podium-spot--place-1 .podium-spot__name {
  font-size: 17px;
}
.podium-spot__time {
  font-variant-numeric: tabular-nums;
  font-size: 13px;
  font-weight: 700;
  color: rgba(255, 255, 255, 0.9);
  letter-spacing: -0.01em;
}
.podium-spot--place-1 .podium-spot__time {
  color: #ffd75e;
  font-size: 16px;
}

/* ── Secondary list (4th place onward, DNFs) ────────────────── */
.results__list {
  list-style: none;
  margin: 0 auto 20px;
  padding: 0;
  display: flex;
  flex-direction: column;
  gap: 6px;
  max-width: 640px;
}
.results__row {
  display: grid;
  grid-template-columns: 34px 28px 1fr auto;
  gap: 12px;
  align-items: center;
  padding: 10px 16px;
  border-radius: 10px;
  background: rgba(255, 255, 255, 0.035);
  border: 1px solid rgba(255, 255, 255, 0.05);
}
.results__row--dnf {
  opacity: 0.6;
  border-style: dashed;
}
.results__place {
  font-size: 15px;
  font-weight: 800;
  font-variant-numeric: tabular-nums;
  text-align: center;
  color: rgba(255, 255, 255, 0.72);
}
.results__row--dnf .results__place {
  font-size: 11px;
  letter-spacing: 0.08em;
  color: rgba(255, 120, 120, 0.85);
}
.results__avatar {
  width: 28px;
  height: 28px;
  border-radius: 50%;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  background: linear-gradient(135deg, #3b5478, #2a3c58);
  color: #fff;
  font-size: 10px;
  font-weight: 700;
  letter-spacing: 0.02em;
}
.results__name {
  font-weight: 600;
  font-size: 14px;
  overflow: hidden;
  white-space: nowrap;
  text-overflow: ellipsis;
}
.results__time {
  font-variant-numeric: tabular-nums;
  font-size: 13px;
  color: rgba(255, 255, 255, 0.72);
}

/* ── Actions ─────────────────────────────── */
.results__actions {
  display: flex;
  gap: 12px;
  justify-content: center;
  /* Anchored tight to the podium so the button doesn't float in empty
     space when there are no 4th-place rows to pad the gap. */
  margin-top: 4px;
  flex-wrap: wrap;
}
.results__back,
.results__rematch {
  display: inline-flex;
  align-items: center;
  padding: 12px 24px;
  border: none;
  border-radius: 10px;
  font-family: inherit;
  font-weight: 700;
  font-size: 14px;
  letter-spacing: 0.02em;
  cursor: pointer;
  transition: filter 0.15s, transform 0.15s;
}
.results__back {
  background: linear-gradient(135deg, #30d66d, #19a34f);
  color: #06130b;
  box-shadow: 0 8px 20px rgba(47, 216, 107, 0.25);
}
.results__back:hover { filter: brightness(1.06); transform: translateY(-1px); }
.results__rematch {
  background: rgba(255, 255, 255, 0.06);
  color: #fff;
  border: 1px solid rgba(255, 255, 255, 0.14);
}
.results__rematch:hover:not(:disabled) {
  background: rgba(255, 255, 255, 0.1);
  transform: translateY(-1px);
}
.results__rematch:disabled { opacity: 0.55; cursor: not-allowed; }

/* ── Responsive tweaks ──────────────────────
   At narrow viewports (phones, split-screen) the podium cards would
   otherwise stack at full width — shrink them proportionally so three
   podium tiles still fit in one row on tablets and wrap cleanly on
   phones. The list rows are already fluid.
*/
@media (max-width: 720px) {
  .podium-spot {
    width: clamp(140px, 32vw, 200px);
  }
  .podium-spot__plinth { padding: 10px 12px; }
  .podium-spot__name { font-size: 14px; }
  .podium-spot--place-1 .podium-spot__name { font-size: 15px; }
  .podium-spot--place-1 .podium-spot__time { font-size: 14px; }
  .podium-spot__medal { width: 30px; height: 30px; font-size: 13px; }
  .results__podium { gap: 10px; }
}
@media (max-width: 480px) {
  /* Single-column podium on phones — keeps each card legible. Winner
     rendered at full width, runners-up side-by-side underneath. */
  .podium-spot { width: 100%; max-width: 320px; }
  .podium-spot--place-1 { max-width: 100%; }
}
</style>
