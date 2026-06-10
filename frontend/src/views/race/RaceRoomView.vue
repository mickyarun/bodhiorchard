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
      <v-card class="cancel-race-card" color="surface">
        <div class="cancel-race-card__eyebrow">
          <CheckerFlagIcon :size="12" />
          Confirm cancellation
        </div>
        <h2 class="cancel-race-card__title">Cancel this race?</h2>
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
            class="cta__pill cta__pill--ghost"
            @click="cancelDialogOpen = false"
          >
            <v-icon icon="mdi-arrow-left" size="16" />
            Keep racing
          </button>
          <button
            type="button"
            class="cta__pill cta__pill--danger"
            @click="confirmCancelAndLeave"
          >
            <v-icon icon="mdi-close-circle-outline" size="16" />
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
  // Fire-and-let-the-echo-drive-us: the server broadcasts `race_cancelled`
  // back to the sender alongside the invitees, so the host's own
  // `onRaceCancelled` handler will surface the toast and schedule the
  // navigation. Avoids a race where `router.push` unmounts the
  // component (closing the WS) before `room.send` has actually flushed
  // the cancel frame.
  client.value?.sendRaceCancel()
}

function leaveImmediate(): void {
  router.push('/dashboard')
}
</script>

<style scoped>
.race-room-view {
  width: 100%;
  height: 100%;
  min-height: calc(100vh - 64px);
  display: flex;
  flex-direction: column;
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
   Reuses the race-error rhythm (eyebrow → italic display title) but
   compressed for a modal. Dark surface lets the AppCallout warning
   tint read as the focal point; the pill actions echo the lobby's
   CTA row so the two surfaces feel like a continuous flow. */
.cancel-race-card {
  padding: 26px 26px 22px;
  border-radius: 14px;
}
.cancel-race-card__eyebrow {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  text-transform: uppercase;
  letter-spacing: 0.2em;
  font-size: 11px;
  color: rgba(255, 255, 255, 0.6);
  font-weight: 600;
  padding: 5px 12px;
  border-radius: 999px;
  background: rgba(255, 255, 255, 0.04);
  border: 1px solid rgba(255, 255, 255, 0.08);
  margin-bottom: 14px;
}
.cancel-race-card__title {
  font-size: clamp(22px, 3vw, 28px);
  font-weight: 900;
  font-style: italic;
  letter-spacing: -0.02em;
  line-height: 1.1;
  margin: 0 0 14px;
}
.cancel-race-card__callout {
  margin-bottom: 18px;
}
.cancel-race-card__actions {
  display: flex;
  justify-content: flex-end;
  gap: 10px;
  flex-wrap: wrap;
}
</style>
