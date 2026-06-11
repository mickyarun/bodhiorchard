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

      <AppCallout
        v-if="error"
        variant="warning"
        eyebrow="Couldn't load"
        class="mx-6 mb-3"
      >
        {{ error }}
      </AppCallout>

      <section class="invite-more__section">
        <MemberPicker
          v-model="selectedIds"
          :members="invitable"
          :max-selection="remainingSlots"
          :loading="loading"
          empty-message="No more members available — everyone in your org is already invited."
        />
      </section>

      <footer class="invite-more__footer">
        <button
          type="button"
          class="cta__pill cta__pill--ghost"
          @click="$emit('update:modelValue', false)"
        >
          Cancel
        </button>
        <button
          type="button"
          class="cta__pill cta__pill--host"
          :disabled="!canSubmit"
          @click="onSend"
        >
          <v-icon icon="mdi-send" size="14" />
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
import MemberPicker, { type MemberPickerEntry } from './MemberPicker.vue'
import AppCallout from '@/components/common/AppCallout.vue'

type DirectoryEntry = MemberPickerEntry

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
  } catch (err) {
    console.error('[RaceInviteMoreDialog] member directory fetch failed:', err)
    error.value = 'Could not load org members. Try again in a moment.'
  } finally {
    loading.value = false
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

.invite-more__footer {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  padding: 12px 16px 16px;
  border-top: 1px solid rgba(255, 255, 255, 0.06);
}

/* Pill visuals (.cta__pill, --host, --ghost, --danger) live in
   assets/styles/race-pills.scss — imported globally via main.scss so
   the silhouette stays consistent across lobby, cancel dialog, and
   this invite-more dialog. */
</style>
