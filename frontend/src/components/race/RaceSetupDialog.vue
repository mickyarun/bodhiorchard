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
  <v-dialog
    :model-value="modelValue"
    max-width="560"
    @update:model-value="$emit('update:modelValue', $event)"
  >
    <div class="setup">
      <RaceThemeBackdrop />

      <header class="setup__header">
        <div class="setup__eyebrow">
          <CheckerFlagIcon :size="12" />
          PRE-RACE SETUP
        </div>
        <h2 class="setup__title">Invite to race</h2>
        <p class="setup__sub">Pick your laps and up to {{ MAX_RACERS - 1 }} rivals to challenge.</p>
      </header>

      <!-- Everything between the pinned header and footer scrolls when the
           dialog is taller than the viewport (small laptop / split screen),
           so the send button can never be pushed off-screen. -->
      <div class="setup__body">

      <v-alert v-if="error" type="error" class="mx-6 mb-4" density="compact">
        {{ error }}
      </v-alert>

      <!-- Lap pills. The race always runs on the one fixed circuit loop;
           the choice is how many times around it. We still send distanceM
           on the wire (lapCount · LOOP_LENGTH_M), so the labels show laps
           but the value the server validates is the existing distance. -->
      <section class="setup__section">
        <div class="setup__section-label">Laps</div>
        <div class="setup__pills" role="radiogroup" aria-label="Race laps">
          <button
            v-for="laps in ALLOWED_LAP_COUNTS"
            :key="laps"
            type="button"
            class="setup__pill"
            :class="{ 'setup__pill--active': distanceM === lapCountToDistanceM(laps) }"
            role="radio"
            :aria-checked="distanceM === lapCountToDistanceM(laps)"
            @click="distanceM = lapCountToDistanceM(laps)"
          >
            <span class="setup__pill-value">{{ laps }}</span>
            <span class="setup__pill-unit">{{ laps === 1 ? 'lap' : 'laps' }}</span>
          </button>
        </div>
      </section>

      <!-- Dev-only: bot test mode (vite dev builds only; the server
           additionally forces botCount to 0 in production). -->
      <section v-if="isDevBuild" class="setup__section">
        <div class="setup__section-label setup__section-label--spaced">Test bots (dev only)</div>
        <AppPillToggle
          v-model="botCount"
          :options="BOT_COUNT_OPTIONS"
        />
      </section>

      <!-- Invitees list -->
      <section class="setup__section">
        <div class="setup__section-head">
          <span class="setup__section-label">Invitees</span>
          <span class="setup__count">
            {{ selectedIds.length }}
            <span class="setup__count-sep">/</span>
            {{ MAX_RACERS - 1 }}
          </span>
        </div>

        <div class="setup__members-container">
          <MemberPicker
            v-model="selectedIds"
            :members="invitableMembers"
            :max-selection="MAX_RACERS - 1"
            :loading="loadingMembers"
            empty-message="No other members available in your org yet."
          />
        </div>
      </section>

      </div>

      <footer class="setup__footer">
        <v-btn variant="text" size="large" @click="$emit('update:modelValue', false)">
          Cancel
        </v-btn>
        <button
          class="setup__send"
          :class="{ 'setup__send--disabled': !canSubmit }"
          :disabled="!canSubmit"
          @click="onSend"
        >
          <v-progress-circular v-if="sending" indeterminate size="18" width="2" color="white" class="mr-2" />
          <v-icon v-else icon="mdi-send" size="18" class="mr-2" />
          Send invites
        </button>
      </footer>
    </div>
  </v-dialog>
</template>

<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import api from '@/services/api'
import { useAuthStore } from '@/stores/auth'
import { OrgRoomClient } from '@/multiplayer/OrgRoomClient'
import {
  ALLOWED_DISTANCES_M,
  ALLOWED_LAP_COUNTS,
  MAX_RACERS,
  lapCountToDistanceM,
} from '@shared/race/RaceConstants'
import AppPillToggle from '@/components/common/AppPillToggle.vue'
import RaceThemeBackdrop from './RaceThemeBackdrop.vue'
import CheckerFlagIcon from './CheckerFlagIcon.vue'
import MemberPicker, { type MemberPickerEntry } from './MemberPicker.vue'

/**
 * Dev-only bot picker: lets a single dev exercise full races without
 * inviting anyone. Rendered only on vite dev builds (isDevBuild) and
 * server-gated besides — production multiplayer forces botCount to 0.
 */
const BOT_COUNT_OPTIONS: Array<{ label: string; value: number }> = [
  { label: 'None', value: 0 },
  { label: '1', value: 1 },
  { label: '3', value: 3 },
  { label: '7', value: 7 },
]
const isDevBuild = import.meta.env.DEV

type DirectoryEntry = MemberPickerEntry

const props = defineProps<{
  modelValue: boolean
  preselectedUserId: string | null
}>()

const emit = defineEmits<{
  (e: 'update:modelValue', open: boolean): void
}>()

const router = useRouter()
const authStore = useAuthStore()

const distanceM = ref<number>(ALLOWED_DISTANCES_M[0])
const botCount = ref<number>(0)
const selectedIds = ref<string[]>([])
const sending = ref(false)
const error = ref<string>('')
const directory = ref<DirectoryEntry[]>([])
const loadingMembers = ref(false)

const invitableMembers = computed(() => {
  // Exclude self + dedup by id (the directory endpoint has been known to
  // return the same record twice when a user has both a legacy and a
  // current profile row).
  const seen = new Set<string>()
  return directory.value.filter(m => {
    if (m.id === authStore.user?.id) return false
    if (seen.has(m.id)) return false
    seen.add(m.id)
    return true
  })
})

// With test bots requested, zero human invitees is a valid solo-dev race
// (bots count toward MIN_RACERS server-side, so host + 1 bot can start).
const canSubmit = computed(() =>
  (selectedIds.value.length >= 1 || botCount.value > 0)
  && selectedIds.value.length <= MAX_RACERS - 1
  && !sending.value,
)

watch(
  () => [props.modelValue, props.preselectedUserId] as const,
  ([open, preId]) => {
    if (!open) return
    error.value = ''
    selectedIds.value = preId ? [preId] : []
    distanceM.value = ALLOWED_DISTANCES_M[0]
    botCount.value = 0
    if (directory.value.length === 0) void loadDirectory()
  },
  { immediate: true },
)

async function loadDirectory(): Promise<void> {
  loadingMembers.value = true
  try {
    const { data } = await api.get<DirectoryEntry[]>('/v1/members/directory')
    directory.value = data
  } catch (err) {
    console.error('[RaceSetupDialog] member directory fetch failed:', err)
    error.value = 'Could not load org members. Try again in a moment.'
  } finally {
    loadingMembers.value = false
  }
}

async function onSend(): Promise<void> {
  if (!canSubmit.value) return
  sending.value = true
  error.value = ''
  try {
    const client = OrgRoomClient.getInstance()
    const { roomId } = await client.sendRaceCreate({
      invitedUserIds: [...selectedIds.value],
      distanceM: distanceM.value,
      // The circuit loop is the only track now — always send 'circuit'.
      // distanceM (100/200) selects 1 or 2 laps over that fixed loop.
      trackShape: 'circuit',
      botCount: botCount.value,
    })
    emit('update:modelValue', false)
    await router.push(`/raceview/${roomId}`)
  } catch (err) {
    console.error('[RaceSetupDialog] send failed:', err)
    error.value = err instanceof Error ? err.message : 'Could not send invites.'
  } finally {
    sending.value = false
  }
}
</script>

<style scoped>
.setup {
  position: relative;
  overflow: hidden;
  /* Cap to the viewport (dvh tracks mobile browser chrome) and lay out as a
     column so the header and footer pin while the body scrolls between them —
     the send button can never be pushed off a short screen. */
  display: flex;
  flex-direction: column;
  max-height: calc(100dvh - 48px);
  border-radius: 18px;
  background: linear-gradient(180deg, #0d1422 0%, #0a0f1a 100%);
  color: #fff;
  font-family: system-ui, -apple-system, 'Segoe UI', sans-serif;
  border: 1px solid rgba(255, 255, 255, 0.08);
  box-shadow: 0 30px 60px rgba(0, 0, 0, 0.5);
  isolation: isolate;
}

/* Backdrop provided by <RaceThemeBackdrop />. */
.setup > *:not(.race-theme-backdrop) {
  position: relative;
  z-index: 1;
}

/* ── Header ───────────────────────────────── */
.setup__header {
  padding: 28px 28px 16px;
  flex-shrink: 0;
}

/* Scroll region between the pinned header and footer. min-height: 0 lets
   this flex item shrink below its content height so overflow engages;
   without it the body grows unbounded and the footer clips off-screen. */
.setup__body {
  flex: 1 1 auto;
  min-height: 0;
  overflow-y: auto;
}
.setup__eyebrow {
  display: inline-flex;
  align-items: center;
  gap: 10px;
  text-transform: uppercase;
  letter-spacing: 0.2em;
  font-size: 11px;
  font-weight: 700;
  color: rgba(255, 255, 255, 0.7);
  padding: 5px 12px;
  border-radius: 999px;
  background: rgba(255, 255, 255, 0.04);
  border: 1px solid rgba(255, 255, 255, 0.08);
  margin-bottom: 10px;
}
.setup__title {
  font-size: 28px;
  font-weight: 900;
  margin: 0;
  letter-spacing: -0.02em;
  font-style: italic;
}
.setup__sub {
  font-size: 13px;
  color: rgba(255, 255, 255, 0.55);
  margin: 4px 0 0;
}

/* ── Sections ─────────────────────────────── */
.setup__section {
  padding: 14px 28px;
}
.setup__section-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 10px;
}
.setup__section-label {
  font-size: 11px;
  font-weight: 700;
  text-transform: uppercase;
  letter-spacing: 0.16em;
  color: rgba(255, 255, 255, 0.65);
}
.setup__count {
  font-size: 12px;
  font-weight: 700;
  font-variant-numeric: tabular-nums;
  color: rgba(255, 255, 255, 0.85);
  padding: 3px 10px;
  border-radius: 999px;
  background: rgba(125, 213, 125, 0.14);
  border: 1px solid rgba(125, 213, 125, 0.25);
}
.setup__count-sep { opacity: 0.4; margin: 0 2px; }

/* Extra top margin for a section label that follows another control
   (e.g. the dev test-bots label under the lap pills). */
.setup__section-label--spaced {
  display: block;
  margin-bottom: 10px;
}

/* Distance pills */
.setup__pills {
  display: flex;
  gap: 10px;
}
.setup__pill {
  flex: 1;
  display: inline-flex;
  align-items: baseline;
  justify-content: center;
  gap: 4px;
  padding: 14px 16px;
  border-radius: 12px;
  border: 1px solid rgba(255, 255, 255, 0.1);
  background: rgba(255, 255, 255, 0.03);
  color: rgba(255, 255, 255, 0.7);
  font-family: inherit;
  cursor: pointer;
  transition: all 0.15s;
}
.setup__pill:hover:not(.setup__pill--active) {
  border-color: rgba(255, 255, 255, 0.2);
  background: rgba(255, 255, 255, 0.06);
}
.setup__pill--active {
  background: linear-gradient(135deg, rgba(255, 215, 94, 0.18), rgba(255, 149, 0, 0.08));
  border-color: rgba(255, 215, 94, 0.45);
  color: #ffd75e;
  box-shadow: 0 8px 24px rgba(255, 149, 0, 0.18);
}
.setup__pill-value {
  font-size: 22px;
  font-weight: 800;
  font-variant-numeric: tabular-nums;
  letter-spacing: -0.02em;
}
.setup__pill-unit {
  font-size: 13px;
  font-weight: 600;
  opacity: 0.7;
}

/* Member list. On a tall screen it caps at 260px and scrolls internally;
   on a short screen the whole dialog body scrolls instead, so the cap
   relaxes (min of the two) to avoid a cramped scrollbox inside a scrollbox. */
.setup__members-container {
  padding: 4px;
  max-height: min(260px, 40dvh);
  overflow-y: auto;
  border-radius: 12px;
  border: 1px solid rgba(255, 255, 255, 0.06);
  background: rgba(0, 0, 0, 0.25);
}
.setup__members-container::-webkit-scrollbar { width: 6px; }
.setup__members-container::-webkit-scrollbar-thumb {
  background: rgba(255, 255, 255, 0.12);
  border-radius: 3px;
}

/* ── Footer ─────────────────────────────── */
.setup__footer {
  display: flex;
  justify-content: flex-end;
  align-items: center;
  gap: 8px;
  padding: 16px 20px 20px;
  border-top: 1px solid rgba(255, 255, 255, 0.06);
  margin-top: 6px;
  flex-shrink: 0;
}
.setup__send {
  display: inline-flex;
  align-items: center;
  padding: 10px 22px;
  border: none;
  border-radius: 10px;
  background: linear-gradient(135deg, #30d66d, #19a34f);
  color: #06130b;
  font-weight: 800;
  font-size: 14px;
  font-family: inherit;
  letter-spacing: 0.02em;
  cursor: pointer;
  transition: filter 0.15s, transform 0.15s, box-shadow 0.15s;
  box-shadow: 0 8px 20px rgba(47, 216, 107, 0.25);
}
.setup__send:hover:not(.setup__send--disabled) {
  filter: brightness(1.06);
  transform: translateY(-1px);
}
.setup__send--disabled {
  background: rgba(255, 255, 255, 0.06);
  color: rgba(255, 255, 255, 0.4);
  cursor: not-allowed;
  box-shadow: none;
}
</style>
