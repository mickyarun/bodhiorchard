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
  <div class="race-room-view">
    <!-- Race-themed empty state. Replaces the bare `v-alert` that used to
         break the visual rhythm of the rest of the lobby/results panels.
         Backdrop + eyebrow + italic title mirror RaceLobbyPanel so the
         page still feels like the race app, not a generic 404. -->
    <div v-if="error" class="race-error">
      <RaceThemeBackdrop />
      <div class="race-error__eyebrow">
        <CheckerFlagIcon :size="12" />
        Race unavailable
      </div>
      <h1 class="race-error__title">This race isn't running</h1>
      <p class="race-error__sub">{{ error }}</p>
      <v-btn
        size="large"
        variant="flat"
        color="primary"
        class="race-error__cta"
        @click="leaveImmediate"
      >
        Back to garden
      </v-btn>
    </div>

    <template v-else-if="snapshot">
      <RaceLobbyPanel
        v-if="snapshot.phase === 'lobby'"
        :snapshot="snapshot"
        :is-host="isHost"
        @start="onStart"
        @leave="goHome"
        @add-invitees="onAddInvitees"
      />
      <RaceLivePanel
        v-else-if="snapshot.phase === 'countdown' || snapshot.phase === 'running'"
        :snapshot="snapshot"
        :client="client!"
        :is-participant="isParticipant"
      />
      <RaceResultsCard
        v-else-if="snapshot.phase === 'finished'"
        :snapshot="snapshot"
        @leave="leaveImmediate"
      />
    </template>

    <div v-else class="pa-6 d-flex align-center justify-center" style="min-height: 200px;">
      <v-progress-circular indeterminate />
    </div>

    <!-- Host back-to-garden gate: leaving the lobby (or the 3 s countdown
         window) before the race actually runs cancels it for every
         invitee, so the destructive default needs explicit confirmation.
         Styled to match the rest of the race chrome: dark surface card,
         AppCallout warning body, pill action row echoing the lobby's
         "Invite more" / "Back to garden" pair. -->
    <v-dialog v-model="cancelDialogOpen" max-width="440">
      <!-- Background, text colour, and gold left rule pinned by
           `.cancel-race-card.v-card` in the scoped style block so the
           dialog stays cinematic-dark under the forest design system's
           auto theme. The eyebrow is dropped — title is the headline,
           no redundant kicker. -->
      <v-card class="cancel-race-card">
        <h2 class="cancel-race-card__title">
          Cancel this race<span class="cancel-race-card__dot">?</span>
        </h2>
        <AppCallout
          variant="warning"
          eyebrow="Affects everyone invited"
          icon="mdi-flag-off-outline"
          class="cancel-race-card__callout"
        >
          Leaving the lobby ends the race for everyone you invited. They'll
          be sent back to the garden.
        </AppCallout>
        <div class="cancel-race-card__actions">
          <button
            type="button"
            class="cancel-race-card__back"
            @click="cancelDialogOpen = false"
          >
            Keep racing
          </button>
          <button
            type="button"
            class="cta__pill cta__pill--danger"
            @click="confirmCancelAndLeave"
          >
            <v-icon icon="mdi-close-circle-outline" size="14" />
            Cancel race
          </button>
        </div>
      </v-card>
    </v-dialog>

    <v-snackbar
      v-model="cancelledToastOpen"
      :timeout="4000"
      color="warning"
      location="top"
    >
      {{ cancelledToastText }}
    </v-snackbar>

    <!-- First-race onboarding for the stamina mechanic. Gated to lobby
         phase + participants so the popup never competes with countdown
         or live-race input. Self-dismissing once the player clicks
         "Got it" (localStorage). -->
    <RaceStaminaIntroDialog :active="staminaIntroActive" />
  </div>
</template>

<script setup lang="ts">
import { computed, onBeforeUnmount, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import { useAuthStore } from '@/stores/auth'
import { RaceRoomClient, type RaceStateSnapshot } from '@/multiplayer/RaceRoomClient'
import RaceLobbyPanel from './RaceLobbyPanel.vue'
import RaceLivePanel from './RaceLivePanel.vue'
import RaceResultsCard from './RaceResultsCard.vue'
import RaceThemeBackdrop from '@/components/race/RaceThemeBackdrop.vue'
import CheckerFlagIcon from '@/components/race/CheckerFlagIcon.vue'
import AppCallout from '@/components/common/AppCallout.vue'
import RaceStaminaIntroDialog from '@/components/race/RaceStaminaIntroDialog.vue'

const props = defineProps<{
  roomId: string
}>()

/**
 * Delay between firing `race_cancel` and navigating away. Long enough for
 * the send to flush over the WebSocket before this view unmounts and
 * closes the socket; short enough to feel instant.
 */
const CANCEL_NAV_DELAY_MS = 250

const router = useRouter()
const authStore = useAuthStore()

const client = ref<RaceRoomClient | null>(null)
const snapshot = ref<RaceStateSnapshot | null>(null)
const error = ref<string>('')
const cancelDialogOpen = ref(false)
const cancelledToastOpen = ref(false)
const cancelledToastText = ref('')

const userId = computed(() => authStore.user?.id ?? '')

const isHost = computed(
  () => !!snapshot.value && snapshot.value.hostUserId === userId.value,
)

const isParticipant = computed(() => {
  if (!snapshot.value) return false
  return snapshot.value.racers.some(r => r.userId === userId.value)
})

// Stamina-intro popup gate: only in the lobby (countdown is too short
// to read; live phase needs the input focus). Spectators don't need
// pacing advice — they're not the ones racing.
const staminaIntroActive = computed(
  () => snapshot.value?.phase === 'lobby' && isParticipant.value,
)

watch(
  () => props.roomId,
  (roomId) => { void connect(roomId) },
  { immediate: true },
)

// Auth can still be loading when the user lands directly on /raceview
// (e.g. deep-linked from an invite email). Retry connect() once the user
// resolves, rather than flashing "You must be signed in" at mount time.
watch(
  () => authStore.user,
  (user) => {
    if (user && !snapshot.value && !error.value) void connect(props.roomId)
  },
)

onBeforeUnmount(() => {
  client.value?.destroy()
  client.value = null
})

async function connect(roomId: string): Promise<void> {
  if (!authStore.user) {
    if (!authStore.isAuthenticated) {
      error.value = 'You must be signed in to view a race.'
    }
    return
  }
  const fresh = new RaceRoomClient()
  fresh.onStateChange = (s) => { snapshot.value = s }
  fresh.onRaceCancelled = ({ hostName }) => {
    cancelledToastText.value = hostName
      ? `${hostName} cancelled the race.`
      : 'The host cancelled the race.'
    cancelledToastOpen.value = true
    // Short delay so the toast is visible during the route change; once
    // the room is gone there's nothing useful to render on this page.
    window.setTimeout(() => router.push('/dashboard'), 1200)
  }
  try {
    await fresh.joinById(roomId, {
      userId: authStore.user.id,
      name: authStore.user.name,
      characterModel: authStore.user.character_model ?? '',
      token: authStore.token ?? '',
    })
    client.value = fresh
  } catch (err) {
    console.error('[RaceRoomView] join failed:', err)
    error.value = 'The host may have cancelled this race, or your invitation has expired.'
    fresh.destroy()
  }
}

function onStart(): void {
  client.value?.sendRaceStart()
}

function onAddInvitees(userIds: string[]): void {
  client.value?.sendAddInvitees(userIds)
}

/**
 * Back-to-garden gate. For the host while the race hasn't actually run
 * yet, this triggers the destructive-action confirmation rather than
 * silently leaving Arun stuck in a "waiting for host" lobby forever.
 * Non-host invitees and post-race viewers just navigate straight.
 */
function goHome(): void {
  if (shouldConfirmCancel.value) {
    cancelDialogOpen.value = true
    return
  }
  leaveImmediate()
}

const shouldConfirmCancel = computed<boolean>(() => {
  if (!isHost.value || !snapshot.value) return false
  const phase = snapshot.value.phase
  return phase === 'lobby' || phase === 'countdown'
})

function confirmCancelAndLeave(): void {
  cancelDialogOpen.value = false
  // Send the cancel, then drive our OWN navigation rather than waiting on
  // the server's `race_cancelled` echo. The echo can never be relied on
  // here: the server broadcasts it and disconnects the room in the same
  // breath, so the frame routinely loses the race to the socket close and
  // the host is left stranded in the lobby. The invitees still get the
  // broadcast (the server defers its disconnect a tick for them); the host
  // doesn't need it — it knows it just cancelled.
  //
  // The short delay before navigating lets the `race_cancel` frame flush
  // over the WS before `router.push` unmounts this view and closes the
  // socket mid-send.
  client.value?.sendRaceCancel()
  window.setTimeout(() => leaveImmediate(), CANCEL_NAV_DELAY_MS)
}

function leaveImmediate(): void {
  router.push('/dashboard')
}
</script>

<style scoped>
.race-room-view {
  /* Race surfaces are deliberately cinematic-dark — pinned regardless
     of the global forest design system theme so the gold/italic chrome
     and white text on lobby + live + results all read against a single
     consistent backdrop. Without this, the forest light theme bleeds
     pale-mint through the page and white/gold elements disappear. */
  width: 100%;
  height: 100%;
  min-height: calc(100vh - 64px);
  display: flex;
  flex-direction: column;
  background: linear-gradient(180deg, #0f1726 0%, #0a0f1a 100%);
  color: #fff;
}
.race-room-view > * {
  flex: 1;
}

/* ── Empty / error state ─────────────────────
   Mirrors RaceLobbyPanel's hero rhythm (pill eyebrow → italic display
   title → descriptive copy → primary CTA) so a missing race feels like
   part of the same app instead of a stack trace. */
.race-error {
  position: relative;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  text-align: center;
  padding: clamp(48px, 8vw, 96px) 24px;
  gap: 18px;
}
.race-error__eyebrow {
  display: inline-flex;
  align-items: center;
  gap: 10px;
  text-transform: uppercase;
  letter-spacing: 0.2em;
  font-size: 12px;
  color: rgba(255, 255, 255, 0.7);
  font-weight: 600;
  padding: 6px 14px;
  border-radius: 999px;
  background: rgba(255, 255, 255, 0.04);
  border: 1px solid rgba(255, 255, 255, 0.08);
}
.race-error__title {
  font-size: clamp(32px, 6vw, 54px);
  font-weight: 900;
  font-style: italic;
  letter-spacing: -0.03em;
  line-height: 1.05;
  margin: 0;
  text-shadow: 0 4px 24px rgba(0, 0, 0, 0.4);
}
.race-error__sub {
  max-width: 460px;
  color: rgba(255, 255, 255, 0.65);
  font-size: 15px;
  line-height: 1.45;
  margin: 0;
}
.race-error__cta {
  margin-top: 8px;
  letter-spacing: 0.05em;
  text-transform: uppercase;
  font-weight: 700;
}

/* ── Cancel-race dialog ─────────────────────
   Cinematic-dark surface pinned (vs. inheriting ``v-card
   color="surface"``) so the modal reads correctly under the forest
   design system's auto light/dark theme. 3px gold left rule is the
   structural anchor — replaces the redundant "Confirm cancellation"
   eyebrow with a single asymmetric mark. Hanging two-line title with
   an accent gold "?" picks up the lobby's question-as-headline voice;
   action row is asymmetric — quiet text "Keep racing" against a red
   danger pill so the destructive default never reads as the safe
   default of a binary choice. */
.cancel-race-card.v-card {
  background: linear-gradient(180deg, #0f1726 0%, #0a0f1a 100%);
  color: #fff;
  border: 1px solid rgba(255, 215, 94, 0.18);
  border-left: 3px solid rgba(255, 215, 94, 0.65);
  border-radius: 14px;
  padding: 26px 28px 22px;
}
.cancel-race-card__title {
  font-size: clamp(28px, 3.6vw, 34px);
  font-weight: 900;
  font-style: italic;
  letter-spacing: -0.025em;
  line-height: 0.98;
  margin: 0 0 18px;
}
.cancel-race-card__dot {
  color: rgba(255, 215, 94, 0.95);
}
.cancel-race-card__callout {
  margin-bottom: 20px;
}
/* AppCallout colours its body with `--v-theme-on-surface`, which follows
   the active forest theme. The card is pinned dark regardless of theme, so
   under light mode that token resolves near-black and the body text reads
   dark-on-dark (invisible). Pin the callout's surface, border, and text to
   the same dark-mode palette the card uses; the gold eyebrow already uses
   the theme-independent warning token, so it's left alone. */
.cancel-race-card__callout {
  /* Root element carries both `.app-callout` and this class, so it keeps
     the parent scope — style it directly (no :deep). */
  border-color: rgba(255, 215, 94, 0.16);
  background: rgba(255, 215, 94, 0.06);
}
/* Inner nodes belong to AppCallout's own scope — reach them with :deep. */
.cancel-race-card__callout :deep(.app-callout__text) {
  color: rgba(255, 255, 255, 0.78);
}
.cancel-race-card__callout :deep(.app-callout__icon) {
  background: rgba(255, 215, 94, 0.14);
}
.cancel-race-card__actions {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
}
.cancel-race-card__back {
  background: transparent;
  border: none;
  padding: 8px 0;
  font-family: inherit;
  font-size: 12px;
  letter-spacing: 0.04em;
  color: rgba(255, 255, 255, 0.55);
  cursor: pointer;
  text-decoration: underline;
  text-decoration-color: rgba(255, 255, 255, 0.2);
  text-underline-offset: 4px;
  transition: color 0.15s, text-decoration-color 0.15s;
}
.cancel-race-card__back:hover {
  color: rgba(255, 255, 255, 0.85);
  text-decoration-color: rgba(255, 215, 94, 0.5);
}
.cancel-race-card__back:focus-visible {
  outline: 2px solid rgba(255, 215, 94, 0.7);
  outline-offset: 4px;
  border-radius: 3px;
}
</style>
