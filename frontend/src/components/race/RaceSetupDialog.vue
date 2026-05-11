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
        <p class="setup__sub">Pick a distance and up to {{ MAX_RACERS - 1 }} rivals to challenge.</p>
      </header>

      <v-alert v-if="error" type="error" class="mx-6 mb-4" density="compact">
        {{ error }}
      </v-alert>

      <!-- Distance pills -->
      <section class="setup__section">
        <div class="setup__section-label">Distance</div>
        <div class="setup__pills" role="radiogroup" aria-label="Race distance">
          <button
            v-for="d in ALLOWED_DISTANCES_M"
            :key="d"
            type="button"
            class="setup__pill"
            :class="{ 'setup__pill--active': distanceM === d }"
            role="radio"
            :aria-checked="distanceM === d"
            @click="distanceM = d"
          >
            <span class="setup__pill-value">{{ d }}</span>
            <span class="setup__pill-unit">m</span>
          </button>
        </div>
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

        <div v-if="loadingMembers" class="d-flex justify-center pa-6">
          <v-progress-circular indeterminate size="28" color="primary" />
        </div>

        <div v-else-if="invitableMembers.length === 0" class="setup__empty">
          No other members available in your org yet.
        </div>

        <ul v-else class="setup__members">
          <li
            v-for="m in invitableMembers"
            :key="m.id"
          >
            <button
              type="button"
              class="setup__member"
              :class="{
                'setup__member--selected': selectedIds.includes(m.id),
                'setup__member--disabled': atCap && !selectedIds.includes(m.id),
              }"
              :disabled="atCap && !selectedIds.includes(m.id)"
              @click="toggle(m.id)"
            >
              <span class="setup__avatar">{{ initials(m.name) }}</span>
              <span class="setup__member-name">{{ m.name }}</span>
              <span class="setup__check" :class="{ 'setup__check--on': selectedIds.includes(m.id) }">
                <v-icon v-if="selectedIds.includes(m.id)" icon="mdi-check" size="14" />
              </span>
            </button>
          </li>
        </ul>
      </section>

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
import { ALLOWED_DISTANCES_M, MAX_RACERS } from '@shared/race/RaceConstants'
import RaceThemeBackdrop from './RaceThemeBackdrop.vue'
import CheckerFlagIcon from './CheckerFlagIcon.vue'
import { initials } from './initials'

interface DirectoryEntry {
  id: string
  name: string
}

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

const atCap = computed(() => selectedIds.value.length >= MAX_RACERS - 1)

const canSubmit = computed(() =>
  selectedIds.value.length >= 1
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

function toggle(id: string): void {
  const i = selectedIds.value.indexOf(id)
  if (i >= 0) {
    selectedIds.value.splice(i, 1)
  } else if (!atCap.value) {
    selectedIds.value.push(id)
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

/* Members list */
.setup__members {
  list-style: none;
  margin: 0;
  padding: 4px;
  display: flex;
  flex-direction: column;
  gap: 4px;
  max-height: 260px;
  overflow-y: auto;
  border-radius: 12px;
  border: 1px solid rgba(255, 255, 255, 0.06);
  background: rgba(0, 0, 0, 0.25);
}
.setup__members::-webkit-scrollbar { width: 6px; }
.setup__members::-webkit-scrollbar-thumb {
  background: rgba(255, 255, 255, 0.12);
  border-radius: 3px;
}
.setup__member {
  width: 100%;
  display: grid;
  grid-template-columns: 32px 1fr 24px;
  align-items: center;
  gap: 12px;
  padding: 8px 12px;
  border: 1px solid transparent;
  border-radius: 8px;
  background: transparent;
  color: inherit;
  font-family: inherit;
  text-align: left;
  cursor: pointer;
  transition: background 0.12s, border-color 0.12s;
}
.setup__member:hover:not(.setup__member--disabled) {
  background: rgba(255, 255, 255, 0.05);
}
.setup__member--selected {
  background: rgba(125, 213, 125, 0.08);
  border-color: rgba(125, 213, 125, 0.3);
}
.setup__member--disabled {
  opacity: 0.35;
  cursor: not-allowed;
}
.setup__avatar {
  width: 32px;
  height: 32px;
  border-radius: 50%;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  font-size: 11px;
  font-weight: 700;
  background: linear-gradient(135deg, #4b7bb0, #2d5680);
  color: #fff;
  letter-spacing: 0.02em;
}
.setup__member--selected .setup__avatar {
  background: linear-gradient(135deg, #7dd57d, #5bae5b);
  color: #06130b;
}
.setup__member-name {
  font-size: 14px;
  font-weight: 600;
  overflow: hidden;
  white-space: nowrap;
  text-overflow: ellipsis;
}
.setup__check {
  width: 22px;
  height: 22px;
  border-radius: 6px;
  border: 1.5px solid rgba(255, 255, 255, 0.2);
  display: inline-flex;
  align-items: center;
  justify-content: center;
  transition: background 0.15s, border-color 0.15s;
}
.setup__check--on {
  background: linear-gradient(135deg, #30d66d, #19a34f);
  border-color: transparent;
  color: #fff;
  box-shadow: 0 4px 12px rgba(47, 216, 107, 0.3);
}

.setup__empty {
  padding: 24px;
  text-align: center;
  color: rgba(255, 255, 255, 0.5);
  font-size: 13px;
  border-radius: 12px;
  border: 1px dashed rgba(255, 255, 255, 0.12);
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
