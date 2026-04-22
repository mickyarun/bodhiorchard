<!-- SPDX-License-Identifier: AGPL-3.0-or-later -->
<!-- Copyright (C) 2026 Arun Rajkumar -->
<template>
  <div class="race-lobby">
    <RaceThemeBackdrop />

    <!-- Header -->
    <header class="race-lobby__header">
      <div class="race-lobby__eyebrow">
        <CheckerFlagIcon />
        {{ snapshot.distanceM }} m sprint
        <span class="race-lobby__dot-sep">·</span>
        <span class="race-lobby__status" :class="{ 'race-lobby__status--ready': canStart }">
          {{ canStart ? 'Ready to race' : 'Waiting for racers' }}
        </span>
      </div>
      <h1 class="race-lobby__title">{{ hostName }}'s race</h1>
    </header>

    <!-- Player grid — each slot hosts a live 3D character preview -->
    <section class="race-lobby__grid" :style="{ '--slot-count': allSlots.length }">
      <article
        v-for="slot in allSlots"
        :key="slot.key"
        class="slot"
        :class="{
          'slot--joined': slot.joined,
          'slot--pending': !slot.joined,
          'slot--host': slot.isHost,
          'slot--self': slot.isSelf,
        }"
      >
        <!-- Lane number corner chip — adds arcade feel -->
        <span class="slot__lane">P{{ slot.lane }}</span>

        <!-- Host crown or pending icon overlay -->
        <span v-if="slot.isHost" class="slot__badge slot__badge--host">
          <v-icon icon="mdi-crown" size="14" /> HOST
        </span>

        <!-- 3D character preview — every slot renders a KayKit model. -->
        <div class="slot__preview">
          <CharacterPreview
            :config="slot.config"
            class="slot__canvas"
          />

          <!-- "Ready" check or "Waiting" pulse sits on top of the preview -->
          <div
            class="slot__status"
            :class="slot.joined ? 'slot__status--ready' : 'slot__status--waiting'"
          >
            <v-icon v-if="slot.joined" icon="mdi-check-circle" size="14" />
            <span v-else class="slot__pulse-dot" />
            {{ slot.joined ? 'Ready' : 'Waiting' }}
          </div>
        </div>

        <!-- Name plate -->
        <div class="slot__plate">
          <div class="slot__name">{{ slot.name }}</div>
          <div class="slot__subline">
            {{ slot.isHost ? 'Host · controls the start'
             : slot.joined   ? 'Locked in'
                             : 'Hasn\'t joined yet' }}
          </div>
        </div>
      </article>
    </section>

    <!-- Prominent status ribbon — what the user is actually waiting for -->
    <footer class="cta">
      <!-- Host: big primary start button with checkered-flag icon -->
      <template v-if="isHost">
        <button
          class="cta__start"
          :class="{ 'cta__start--disabled': !canStart }"
          :disabled="!canStart"
          @click="$emit('start')"
        >
          <span class="cta__start-icon" aria-hidden="true">
            <v-icon icon="mdi-flag-checkered" size="28" />
          </span>
          <span class="cta__start-label">
            <span class="cta__start-eyebrow">{{ canStart ? 'Everyone is in' : `Need ${Math.max(0, MIN_RACERS - snapshot.racers.length)} more` }}</span>
            <span class="cta__start-main">START RACE</span>
          </span>
          <span class="cta__start-chevrons" aria-hidden="true">▶▶▶</span>
        </button>
      </template>

      <!-- Non-host: big animated "waiting for host" loader -->
      <div v-else class="cta__wait">
        <div class="cta__wait-ring" aria-hidden="true">
          <div class="cta__wait-core" />
          <svg class="cta__wait-spinner" viewBox="0 0 52 52">
            <circle class="cta__wait-track" cx="26" cy="26" r="22" />
            <circle class="cta__wait-arc" cx="26" cy="26" r="22" />
          </svg>
        </div>
        <div class="cta__wait-text">
          <div class="cta__wait-eyebrow">Waiting for host</div>
          <div class="cta__wait-main">{{ hostName }} will start the race</div>
          <div class="cta__wait-sub">Hold tight — the track is being prepped</div>
        </div>
      </div>

      <v-btn class="cta__leave" variant="text" size="large" @click="$emit('leave')">
        Back to garden
      </v-btn>
    </footer>
  </div>
</template>

<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import type { RaceStateSnapshot } from '@/multiplayer/RaceRoomClient'
import { MIN_RACERS } from '@shared/race/RaceConstants'
import { OrgRoomClient } from '@/multiplayer/OrgRoomClient'
import { useAuthStore } from '@/stores/auth'
import { parseCharacterModel, type CharacterConfig } from '@/engine/characters/CharacterConfig'
import CharacterPreview from '@/components/character/CharacterPreview.vue'
import RaceThemeBackdrop from '@/components/race/RaceThemeBackdrop.vue'
import CheckerFlagIcon from '@/components/race/CheckerFlagIcon.vue'

const props = defineProps<{
  snapshot: RaceStateSnapshot
  isHost: boolean
}>()

defineEmits<{
  (e: 'start'): void
  (e: 'leave'): void
}>()

const authStore = useAuthStore()

const hostName = computed(() => props.snapshot.hostName || 'Unknown host')

const pendingInvitees = computed(() => {
  const joined = new Set(props.snapshot.racers.map(r => r.userId))
  return props.snapshot.invitedUserIds.filter(id => !joined.has(id))
})

const canStart = computed(() => props.snapshot.racers.length >= MIN_RACERS)

/**
 * Names + character models for pending invitees live on the *org* room's
 * member snapshots, not on the race-room schema. The tick counter makes
 * `nameFor` / `configFor` reactive to member add/update events so the
 * lobby fills in as members stream in from the org room.
 */
const orgMemberTick = ref(0)
let unsubscribeMemberListener: (() => void) | null = null

onMounted(() => {
  const org = OrgRoomClient.getInstance()
  unsubscribeMemberListener = org.addMemberChangeListener(() => {
    orgMemberTick.value++
  })
})
onBeforeUnmount(() => {
  unsubscribeMemberListener?.()
  unsubscribeMemberListener = null
})

function nameFor(userId: string): string {
  void orgMemberTick.value
  const member = OrgRoomClient.getInstance().getMember(userId)
  if (member?.name) return member.name
  return userId.length > 12 ? `${userId.slice(0, 8)}…` : userId
}

/**
 * Every slot gets a renderable character, even pending invitees whose
 * OrgRoom snapshot hasn't arrived — `parseCharacterModel` returns the
 * default KayKit config for any falsy input. The UI still
 * distinguishes joined vs waiting via the status chip / accent bar.
 */
function configFor(userId: string, rawModel: string | null): CharacterConfig {
  void orgMemberTick.value
  if (rawModel) return parseCharacterModel(rawModel)
  const member = OrgRoomClient.getInstance().getMember(userId)
  return parseCharacterModel(member?.characterModel ?? '')
}

interface LobbySlot {
  key: string
  lane: number
  name: string
  joined: boolean
  isHost: boolean
  isSelf: boolean
  config: CharacterConfig
}

/** Joined racers first (by laneIndex), then pending invitees. */
const allSlots = computed<LobbySlot[]>(() => {
  const selfId = authStore.user?.id ?? ''
  const joinedSlots: LobbySlot[] = props.snapshot.racers.map((r, idx) => ({
    key: `r-${r.userId}`,
    lane: (r.laneIndex ?? idx) + 1,
    name: r.name,
    joined: true,
    isHost: r.userId === props.snapshot.hostUserId,
    isSelf: r.userId === selfId,
    config: configFor(r.userId, r.characterModel),
  }))
  const pendingSlots: LobbySlot[] = pendingInvitees.value.map((id, idx) => ({
    key: `p-${id}`,
    lane: joinedSlots.length + idx + 1,
    name: nameFor(id),
    joined: false,
    isHost: false,
    isSelf: id === selfId,
    config: configFor(id, null),
  }))
  return [...joinedSlots, ...pendingSlots]
})
</script>

<style scoped>
.race-lobby {
  position: relative;
  min-height: 100%;
  padding: 40px 24px 32px;
  font-family: system-ui, -apple-system, 'Segoe UI', sans-serif;
  color: #fff;
  isolation: isolate;
  /* overflow-x hidden to clip the bg stripes sideways, but y-auto so the
     page scrolls when content exceeds viewport (CTA used to clip). */
  overflow-x: hidden;
  overflow-y: auto;
}

/* Keep all direct children above the shared RaceThemeBackdrop (z:0).
   Width capping is applied per-section so the grid can go wider than
   the header/CTA when the lobby holds lots of racers. */
.race-lobby > *:not(.race-theme-backdrop) {
  position: relative;
  z-index: 1;
}
.race-lobby__header,
.cta {
  max-width: 720px;
  margin-left: auto;
  margin-right: auto;
}

/* ── Header ───────────────────────────────── */
.race-lobby__header {
  text-align: center;
  margin-bottom: 28px;
}
.race-lobby__eyebrow {
  display: inline-flex;
  align-items: center;
  gap: 10px;
  text-transform: uppercase;
  letter-spacing: 0.2em;
  font-size: 12px;
  color: rgba(255, 255, 255, 0.7);
  font-weight: 600;
  margin-bottom: 8px;
  padding: 6px 14px;
  border-radius: 999px;
  background: rgba(255, 255, 255, 0.04);
  border: 1px solid rgba(255, 255, 255, 0.08);
}
.race-lobby__dot-sep { opacity: 0.4; }
.race-lobby__status { color: #ffd75e; }
.race-lobby__status--ready { color: #7dff9d; }
.race-lobby__title {
  font-size: clamp(32px, 6vw, 54px);
  font-weight: 900;
  margin: 0;
  letter-spacing: -0.03em;
  line-height: 1;
  text-shadow: 0 4px 24px rgba(0, 0, 0, 0.4);
  font-style: italic;
}

/* ── Slot grid ────────────────────────────── */
/* Force every slot onto one line — up to MAX_RACERS=10. `minmax(0, 1fr)`
   lets columns shrink below their intrinsic content size so 10 cards fit
   in narrow viewports without wrapping. Cap total width so 2 cards don't
   stretch across the whole page. */
.race-lobby__grid {
  display: grid;
  gap: 14px;
  grid-template-columns: repeat(var(--slot-count, 2), minmax(0, 1fr));
  margin-bottom: 32px;
  max-width: min(1280px, calc(var(--slot-count, 2) * 280px));
  margin-left: auto;
  margin-right: auto;
}

.slot {
  position: relative;
  display: flex;
  flex-direction: column;
  padding: 12px 12px 14px;
  border-radius: 14px;
  min-width: 0; /* allow grid item to shrink below content size */
  background: linear-gradient(180deg, rgba(18, 26, 40, 0.72), rgba(10, 14, 22, 0.6));
  border: 1px solid rgba(255, 255, 255, 0.08);
  backdrop-filter: blur(10px);
  box-shadow: 0 18px 40px rgba(0, 0, 0, 0.35);
  transition: transform 0.2s, border-color 0.2s, box-shadow 0.2s;
  overflow: hidden;
}
.slot::before {
  /* thin top accent bar — colour signals state */
  content: '';
  position: absolute;
  top: 0; left: 0; right: 0;
  height: 3px;
  background: rgba(255, 255, 255, 0.08);
  transition: background 0.2s;
}
.slot--joined::before { background: linear-gradient(90deg, #7dff9d, #2fd86b); }
.slot--host::before   { background: linear-gradient(90deg, #ffd75e, #ff9500); }
.slot--pending::before {
  background: repeating-linear-gradient(90deg, rgba(255,255,255,0.25) 0 8px, transparent 8px 16px);
}
.slot--self {
  border-color: rgba(120, 180, 255, 0.35);
  box-shadow: 0 18px 40px rgba(0, 0, 0, 0.35), 0 0 0 1px rgba(120, 180, 255, 0.15), 0 0 28px rgba(120, 180, 255, 0.1);
}
.slot--joined:hover { transform: translateY(-2px); }

.slot__lane {
  position: absolute;
  top: 10px;
  left: 10px;
  font-weight: 800;
  font-size: 10px;
  letter-spacing: 0.08em;
  padding: 2px 6px;
  border-radius: 5px;
  background: rgba(0, 0, 0, 0.55);
  border: 1px solid rgba(255, 255, 255, 0.08);
  color: rgba(255, 255, 255, 0.85);
  z-index: 2;
}
.slot__badge {
  position: absolute;
  top: 10px;
  right: 10px;
  display: inline-flex;
  align-items: center;
  gap: 3px;
  font-size: 9px;
  font-weight: 800;
  letter-spacing: 0.08em;
  padding: 3px 6px;
  border-radius: 5px;
  z-index: 2;
}
.slot__badge--host {
  background: linear-gradient(135deg, rgba(255, 215, 94, 0.25), rgba(255, 149, 0, 0.25));
  color: #ffd75e;
  border: 1px solid rgba(255, 215, 94, 0.4);
}

/* 3D preview area — relaxes the component's default min-height. */
.slot__preview {
  position: relative;
  aspect-ratio: 4 / 5;
  border-radius: 10px;
  overflow: hidden;
  background:
    radial-gradient(ellipse at 50% 70%, rgba(100, 140, 200, 0.18), transparent 60%),
    linear-gradient(180deg, #0c1320 0%, #070a12 100%);
  margin-bottom: 10px;
  margin-top: 26px; /* clear the lane/badge chips */
}
.slot__preview::after {
  /* soft bottom vignette so the name plate doesn't fight the render */
  content: '';
  position: absolute;
  inset: 0;
  pointer-events: none;
  background: linear-gradient(180deg, transparent 70%, rgba(0, 0, 0, 0.35) 100%);
}
.slot__canvas,
.slot__canvas :deep(.character-preview) {
  width: 100%;
  height: 100%;
  min-height: 0 !important;
  background: transparent;
  border-radius: 0;
}

.slot__placeholder {
  position: absolute;
  inset: 0;
  display: flex;
  align-items: center;
  justify-content: center;
  color: rgba(255, 255, 255, 0.28);
  background: repeating-linear-gradient(
    135deg,
    transparent 0 8px,
    rgba(255, 255, 255, 0.03) 8px 9px
  );
}

/* Ready / Waiting chip floating on the preview */
.slot__status {
  position: absolute;
  bottom: 10px;
  left: 10px;
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 4px 10px;
  border-radius: 999px;
  font-size: 11px;
  font-weight: 700;
  letter-spacing: 0.08em;
  text-transform: uppercase;
  backdrop-filter: blur(6px);
}
.slot__status--ready {
  background: rgba(47, 216, 107, 0.2);
  color: #7dff9d;
  border: 1px solid rgba(47, 216, 107, 0.35);
}
.slot__status--waiting {
  background: rgba(255, 255, 255, 0.08);
  color: rgba(255, 255, 255, 0.75);
  border: 1px solid rgba(255, 255, 255, 0.12);
}
.slot__pulse-dot {
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background: #ffd75e;
  animation: slot-pulse 1.3s ease-in-out infinite;
}
@keyframes slot-pulse {
  0%, 100% { opacity: 0.3; transform: scale(0.9); }
  50%      { opacity: 1;   transform: scale(1.2); }
}

.slot__plate {
  text-align: left;
  min-width: 0;
}
.slot__name {
  font-size: 14px;
  font-weight: 700;
  letter-spacing: -0.01em;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.slot--pending .slot__name { color: rgba(255, 255, 255, 0.65); }
.slot__subline {
  font-size: 10px;
  color: rgba(255, 255, 255, 0.5);
  margin-top: 2px;
  letter-spacing: 0.02em;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.slot__status {
  font-size: 10px;
  padding: 3px 8px;
}

/* ── CTA ─────────────────────────────────── */
.cta {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 16px;
  max-width: 720px;
  margin: 0 auto;
}

/* Host start button */
.cta__start {
  position: relative;
  display: inline-flex;
  align-items: center;
  gap: 16px;
  min-width: 380px;
  padding: 16px 28px;
  border: none;
  border-radius: 14px;
  background: linear-gradient(135deg, #30d66d, #19a34f);
  color: #06130b;
  font-family: inherit;
  cursor: pointer;
  box-shadow:
    0 10px 28px rgba(47, 216, 107, 0.35),
    0 0 0 1px rgba(255, 255, 255, 0.1) inset;
  transition: transform 0.15s, box-shadow 0.15s, filter 0.15s;
  overflow: hidden;
}
.cta__start:hover:not(.cta__start--disabled) {
  transform: translateY(-1px);
  filter: brightness(1.06);
  box-shadow: 0 14px 32px rgba(47, 216, 107, 0.45), 0 0 0 1px rgba(255, 255, 255, 0.1) inset;
}
.cta__start:active:not(.cta__start--disabled) { transform: translateY(0); }
.cta__start--disabled {
  background: rgba(255, 255, 255, 0.06);
  color: rgba(255, 255, 255, 0.5);
  cursor: not-allowed;
  box-shadow: none;
}
.cta__start-icon {
  display: inline-flex;
  width: 48px;
  height: 48px;
  align-items: center;
  justify-content: center;
  border-radius: 10px;
  background: rgba(255, 255, 255, 0.2);
  color: #06130b;
}
.cta__start--disabled .cta__start-icon {
  background: rgba(255, 255, 255, 0.04);
  color: rgba(255, 255, 255, 0.4);
}
.cta__start-label {
  flex: 1;
  display: flex;
  flex-direction: column;
  align-items: flex-start;
  line-height: 1;
}
.cta__start-eyebrow {
  font-size: 11px;
  letter-spacing: 0.14em;
  text-transform: uppercase;
  opacity: 0.8;
  margin-bottom: 6px;
  font-weight: 700;
}
.cta__start-main {
  font-size: 24px;
  font-weight: 900;
  letter-spacing: 0.02em;
  font-style: italic;
}
.cta__start-chevrons {
  font-size: 16px;
  letter-spacing: 0.1em;
  opacity: 0.7;
  animation: chevron-slide 1.1s linear infinite;
}
.cta__start--disabled .cta__start-chevrons { animation: none; opacity: 0.25; }
@keyframes chevron-slide {
  0%   { transform: translateX(-4px); opacity: 0.3; }
  50%  { opacity: 0.9; }
  100% { transform: translateX(4px);  opacity: 0.3; }
}

/* Non-host waiting ring */
.cta__wait {
  display: inline-flex;
  align-items: center;
  gap: 20px;
  min-width: 380px;
  padding: 18px 24px;
  border-radius: 16px;
  background: linear-gradient(180deg, rgba(18, 26, 40, 0.8), rgba(10, 14, 22, 0.7));
  border: 1px solid rgba(255, 215, 94, 0.2);
  box-shadow: 0 18px 40px rgba(0, 0, 0, 0.4), 0 0 32px rgba(255, 215, 94, 0.08);
  backdrop-filter: blur(10px);
}
.cta__wait-ring {
  position: relative;
  width: 52px;
  height: 52px;
  flex-shrink: 0;
}
.cta__wait-core {
  position: absolute;
  inset: 14px;
  border-radius: 50%;
  background: radial-gradient(circle, #ffd75e, #ff9500);
  box-shadow: 0 0 16px rgba(255, 215, 94, 0.6);
  animation: wait-core-pulse 1.4s ease-in-out infinite;
}
@keyframes wait-core-pulse {
  0%, 100% { transform: scale(0.85); opacity: 0.8; }
  50%      { transform: scale(1);    opacity: 1;   }
}
.cta__wait-spinner {
  position: absolute;
  inset: 0;
  transform: rotate(-90deg);
  animation: wait-spin 2.6s linear infinite;
}
@keyframes wait-spin { to { transform: rotate(270deg); } }
.cta__wait-track {
  fill: none;
  stroke: rgba(255, 255, 255, 0.08);
  stroke-width: 3;
}
.cta__wait-arc {
  fill: none;
  stroke: #ffd75e;
  stroke-width: 3;
  stroke-linecap: round;
  stroke-dasharray: 30 200;
  filter: drop-shadow(0 0 6px rgba(255, 215, 94, 0.6));
}
.cta__wait-text {
  display: flex;
  flex-direction: column;
  text-align: left;
}
.cta__wait-eyebrow {
  font-size: 11px;
  text-transform: uppercase;
  letter-spacing: 0.18em;
  color: #ffd75e;
  font-weight: 700;
}
.cta__wait-main {
  font-size: 18px;
  font-weight: 700;
  margin-top: 3px;
  letter-spacing: -0.01em;
}
.cta__wait-sub {
  font-size: 12px;
  color: rgba(255, 255, 255, 0.55);
  margin-top: 2px;
}

.cta__leave {
  margin-top: 4px;
  opacity: 0.7;
}
.cta__leave:hover { opacity: 1; }
</style>
