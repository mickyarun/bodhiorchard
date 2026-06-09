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
  Danger Zone card on /settings/code. Houses destructive recovery
  actions that admins should never need under normal operation:
  currently only "rerun skill profiles", which wipes every
  ``skill_profiles`` row for the org and recomputes from git history.
  Used to clean up orphan rows under deactivated users after a botched
  member merge has been corrected via Settings → Members.

  The submit button stays disabled until the admin types the exact
  confirmation phrase shown above the input.
-->
<template>
  <v-card variant="outlined" class="danger-zone mt-6">
    <v-card-title class="d-flex align-center ga-2 text-error">
      <v-icon icon="mdi-alert-octagon-outline" />
      <span class="text-body-1 font-weight-medium">Danger Zone</span>
    </v-card-title>
    <v-divider />

    <div class="pa-5">
      <div class="text-body-2 font-weight-medium mb-1">Rerun skill profiles</div>
      <div class="text-caption text-medium-emphasis mb-3">
        Deletes every row in <code>skill_profiles</code> for this organization
        and recomputes from git history across all active repositories. Use
        this after correcting a bad alias merge in Settings → Members — it
        clears orphaned attribution under deactivated users. Skill profiles
        are unavailable until the rerun finishes (typically seconds, up to a
        minute for very large orgs).
      </div>

      <v-alert
        v-if="lastResult"
        type="success"
        variant="tonal"
        density="compact"
        class="mb-3"
        closable
        @click:close="lastResult = null"
      >
        Wiped {{ lastResult.profilesDeleted }}, upserted
        {{ lastResult.profilesUpserted }} across {{ lastResult.reposWalked }}
        repo(s); {{ lastResult.unmatchedEmails }} unmatched email(s).
      </v-alert>

      <v-alert
        v-if="errorMessage"
        type="error"
        variant="tonal"
        density="compact"
        class="mb-3"
        closable
        @click:close="errorMessage = null"
      >
        {{ errorMessage }}
      </v-alert>

      <v-alert
        v-if="running"
        type="info"
        variant="tonal"
        density="compact"
        class="mb-3"
      >
        <div class="d-flex align-center ga-2">
          <v-progress-circular indeterminate size="16" width="2" />
          <span>{{ progressMessage || 'Walking repositories…' }}</span>
        </div>
        <v-progress-linear
          v-if="progressPct > 0"
          :model-value="progressPct"
          height="4"
          color="info"
          class="mt-2"
          rounded
        />
      </v-alert>

      <div class="text-caption text-medium-emphasis mb-2">
        Type
        <code class="confirm-phrase">{{ settingsStore.SKILL_RERUN_CONFIRMATION }}</code>
        below to enable the button.
      </div>
      <v-text-field
        v-model="typedConfirmation"
        density="compact"
        variant="outlined"
        hide-details
        :placeholder="settingsStore.SKILL_RERUN_CONFIRMATION"
        :disabled="running"
        class="mb-3"
      />

      <v-btn
        color="error"
        variant="flat"
        prepend-icon="mdi-refresh"
        class="text-none"
        :loading="running"
        :disabled="!canSubmit"
        @click="onSubmit"
      >
        Wipe &amp; recompute skill profiles
      </v-btn>
    </div>
  </v-card>
</template>

<script setup lang="ts">
import { computed, onUnmounted, ref } from 'vue'
import { useSettingsStore } from '@/stores/settings'
import { useJobSocket } from '@/composables/useJobSocket'

interface SkillRerunResult {
  profilesDeleted: number
  profilesUpserted: number
  unmatchedEmails: number
  reposWalked: number
}

const settingsStore = useSettingsStore()
const { startTracking, stopTracking } = useJobSocket()

const typedConfirmation = ref('')
const running = ref(false)
const progressMessage = ref('')
const progressPct = ref(0)
const errorMessage = ref<string | null>(null)
const lastResult = ref<SkillRerunResult | null>(null)

const canSubmit = computed(
  () =>
    typedConfirmation.value.trim() === settingsStore.SKILL_RERUN_CONFIRMATION
    && !running.value,
)

function reset() {
  running.value = false
  progressMessage.value = ''
  progressPct.value = 0
}

async function onSubmit() {
  if (!canSubmit.value) return
  running.value = true
  errorMessage.value = null
  lastResult.value = null
  progressMessage.value = 'Starting…'
  progressPct.value = 0

  const created = await settingsStore.rerunSkillProfiles(typedConfirmation.value)
  // HMR-stale store body once handed back the bare object instead of the
  // jobId string, producing /jobs/[object Object]/status. Narrow defensively.
  const jobId = typeof created?.jobId === 'string' ? created.jobId : null
  if (!jobId) {
    reset()
    errorMessage.value = settingsStore.error
      ?? (created ? 'Server did not return a job id.' : 'Failed to start skill rerun.')
    return
  }

  startTracking(jobId, {
    onProgress: (snapshot) => {
      if (snapshot.statusMessage) progressMessage.value = snapshot.statusMessage
      if (typeof snapshot.progressPct === 'number') progressPct.value = snapshot.progressPct
    },
    onComplete: (snapshot) => {
      reset()
      typedConfirmation.value = ''
      const result = snapshot.result as SkillRerunResult | undefined
      if (result) lastResult.value = result
    },
    onError: (message) => {
      reset()
      errorMessage.value = message || 'Skill rerun failed.'
    },
  })
}

// If the user navigates away mid-run the websocket subscription is
// still useful — the worker keeps going — but the tracker callbacks
// would fire into a torn-down component, leaking warnings. Stop here.
onUnmounted(() => stopTracking())
</script>

<style scoped>
.danger-zone {
  border-color: rgba(var(--v-theme-error), 0.4);
}
.confirm-phrase {
  font-weight: 600;
  letter-spacing: 0.02em;
}
</style>
