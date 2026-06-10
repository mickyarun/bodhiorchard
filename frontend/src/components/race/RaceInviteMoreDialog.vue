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
  Lobby-side "Invite more" dialog. Distinct from RaceSetupDialog
  because (a) distance is already locked when the race exists, (b) the
  invitee list must exclude users already in the room (current racers +
  pending invitees + self), and (c) the parent owns the actual send —
  it routes through RaceRoomClient, not OrgRoomClient.
-->
<template>
  <v-dialog
    :model-value="modelValue"
    max-width="520"
    @update:model-value="$emit('update:modelValue', $event)"
  >
    <div class="invite-more">
      <RaceThemeBackdrop />

      <header class="invite-more__header">
        <div class="invite-more__eyebrow">
          <CheckerFlagIcon :size="12" />
          Add to race
        </div>
        <h2 class="invite-more__title">Invite more racers</h2>
        <p class="invite-more__sub">
          Up to {{ remainingSlots }} more {{ remainingSlots === 1 ? 'racer' : 'racers' }}
          can join.
        </p>
      </header>

      <v-alert v-if="error" type="error" class="mx-6 mb-4" density="compact">
        {{ error }}
      </v-alert>

      <section class="invite-more__section">
        <div v-if="loading" class="d-flex justify-center pa-6">
          <v-progress-circular indeterminate size="28" color="primary" />
        </div>

        <div v-else-if="invitable.length === 0" class="invite-more__empty">
          No more members available — everyone in your org is already invited.
        </div>

        <ul v-else class="invite-more__list">
          <li v-for="m in invitable" :key="m.id">
            <button
              type="button"
              class="invite-more__member"
              :class="{
                'invite-more__member--selected': selectedIds.includes(m.id),
                'invite-more__member--disabled': atCap && !selectedIds.includes(m.id),
              }"
              :disabled="atCap && !selectedIds.includes(m.id)"
              @click="toggle(m.id)"
            >
              <span class="invite-more__avatar">{{ initials(m.name) }}</span>
              <span class="invite-more__text">
                <span class="invite-more__name">{{ m.name }}</span>
                <span class="invite-more__email">{{ m.email }}</span>
              </span>
              <span
                class="invite-more__check"
                :class="{ 'invite-more__check--on': selectedIds.includes(m.id) }"
              >
                <v-icon v-if="selectedIds.includes(m.id)" icon="mdi-check" size="14" />
              </span>
            </button>
          </li>
        </ul>
      </section>

      <footer class="invite-more__footer">
        <v-btn variant="text" size="large" @click="$emit('update:modelValue', false)">
          Cancel
        </v-btn>
        <button
          class="invite-more__send"
          :class="{ 'invite-more__send--disabled': !canSubmit }"
          :disabled="!canSubmit"
          @click="onSend"
        >
          <v-icon icon="mdi-send" size="18" class="mr-2" />
          Send invites
        </button>
      </footer>
    </div>
  </v-dialog>
</template>

<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import api from '@/services/api'
import { useAuthStore } from '@/stores/auth'
import RaceThemeBackdrop from './RaceThemeBackdrop.vue'
import CheckerFlagIcon from './CheckerFlagIcon.vue'
import { initials } from './initials'

interface DirectoryEntry {
  id: string
  name: string
  email: string
}

const props = defineProps<{
  modelValue: boolean
  /** Already-known user ids — racers + pending invitees. Excluded from picker. */
  excludeUserIds: string[]
  /** MAX_RACERS minus current participants — caps the selection. */
  remainingSlots: number
}>()

const emit = defineEmits<{
  (e: 'update:modelValue', open: boolean): void
  (e: 'send', userIds: string[]): void
}>()

const authStore = useAuthStore()

const selectedIds = ref<string[]>([])
const error = ref<string>('')
const directory = ref<DirectoryEntry[]>([])
const loading = ref(false)

const excludeSet = computed(() => {
  const s = new Set(props.excludeUserIds)
  const me = authStore.user?.id
  if (me) s.add(me)
  return s
})

const invitable = computed(() => {
  // Dedup by id — the directory endpoint has been known to return the
  // same record twice when a user has both a legacy and a current
  // profile row (mirrors the guard in RaceSetupDialog).
  const seen = new Set<string>()
  return directory.value.filter(m => {
    if (excludeSet.value.has(m.id)) return false
    if (seen.has(m.id)) return false
    seen.add(m.id)
    return true
  })
})

const atCap = computed(() => selectedIds.value.length >= props.remainingSlots)
const canSubmit = computed(() => selectedIds.value.length > 0 && !loading.value)

watch(
  () => props.modelValue,
  (open) => {
    if (!open) return
    selectedIds.value = []
    error.value = ''
    if (directory.value.length === 0) void loadDirectory()
  },
  { immediate: true },
)

async function loadDirectory(): Promise<void> {
  loading.value = true
  try {
    const { data } = await api.get<DirectoryEntry[]>('/v1/members/directory')
    directory.value = data
  } catch {
    error.value = 'Could not load org members. Try again in a moment.'
  } finally {
    loading.value = false
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

function onSend(): void {
  if (!canSubmit.value) return
  emit('send', [...selectedIds.value])
  emit('update:modelValue', false)
}
</script>

<style scoped>
.invite-more {
  position: relative;
  border-radius: 16px;
  border: 1px solid rgba(255, 215, 94, 0.18);
  background: linear-gradient(180deg, #0f1726 0%, #0a0f1a 100%);
  color: #fff;
  overflow: hidden;
  isolation: isolate;
}
.invite-more > *:not(.race-theme-backdrop) { position: relative; z-index: 1; }

.invite-more__header {
  text-align: center;
  padding: 24px 24px 12px;
}
.invite-more__eyebrow {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  text-transform: uppercase;
  letter-spacing: 0.2em;
  font-size: 11px;
  color: rgba(255, 215, 94, 0.85);
  font-weight: 700;
  padding: 5px 12px;
  border-radius: 999px;
  background: rgba(255, 215, 94, 0.08);
  border: 1px solid rgba(255, 215, 94, 0.18);
  margin-bottom: 12px;
}
.invite-more__title {
  margin: 0;
  font-size: 26px;
  font-weight: 800;
  font-style: italic;
  letter-spacing: -0.01em;
}
.invite-more__sub {
  margin: 6px 0 0;
  font-size: 13px;
  color: rgba(255, 255, 255, 0.6);
}

.invite-more__section {
  padding: 8px 16px 16px;
  max-height: 360px;
  overflow-y: auto;
}
.invite-more__empty {
  text-align: center;
  padding: 24px;
  color: rgba(255, 255, 255, 0.55);
  font-size: 13px;
}
.invite-more__list {
  list-style: none;
  padding: 0;
  margin: 0;
  display: flex;
  flex-direction: column;
  gap: 4px;
}
.invite-more__member {
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
.invite-more__member:hover:not(.invite-more__member--disabled) {
  background: rgba(255, 255, 255, 0.05);
}
.invite-more__member--selected {
  background: rgba(125, 213, 125, 0.08);
  border-color: rgba(125, 213, 125, 0.3);
}
.invite-more__member--disabled {
  opacity: 0.35;
  cursor: not-allowed;
}
.invite-more__avatar {
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
.invite-more__member--selected .invite-more__avatar {
  background: linear-gradient(135deg, #7dd57d, #5bae5b);
  color: #06130b;
}
.invite-more__text {
  display: flex;
  flex-direction: column;
  min-width: 0;
}
.invite-more__name {
  font-size: 14px;
  font-weight: 600;
  overflow: hidden;
  white-space: nowrap;
  text-overflow: ellipsis;
}
.invite-more__email {
  font-size: 11px;
  color: rgba(255, 255, 255, 0.45);
  overflow: hidden;
  white-space: nowrap;
  text-overflow: ellipsis;
  margin-top: 1px;
}
.invite-more__check {
  width: 22px;
  height: 22px;
  border-radius: 6px;
  border: 1.5px solid rgba(255, 255, 255, 0.2);
  display: inline-flex;
  align-items: center;
  justify-content: center;
  transition: background 0.15s, border-color 0.15s;
}
.invite-more__check--on {
  background: linear-gradient(135deg, #30d66d, #19a34f);
  border-color: transparent;
  color: #fff;
}

.invite-more__footer {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  padding: 12px 16px 16px;
  border-top: 1px solid rgba(255, 255, 255, 0.06);
}
.invite-more__send {
  display: inline-flex;
  align-items: center;
  padding: 10px 22px;
  border: none;
  border-radius: 8px;
  background: linear-gradient(135deg, #30d66d, #19a34f);
  color: #06130b;
  font-family: inherit;
  font-weight: 800;
  font-size: 14px;
  letter-spacing: 0.04em;
  cursor: pointer;
  box-shadow: 0 6px 16px rgba(47, 216, 107, 0.3);
}
.invite-more__send--disabled {
  opacity: 0.4;
  cursor: not-allowed;
  box-shadow: none;
}
</style>
