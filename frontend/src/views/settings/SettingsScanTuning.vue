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
  Per-org scan-pipeline tuning. Synth and merge each get their own
  timeout because synth runs many short calls in parallel while merge
  runs one long call over the union of features — sharing a ceiling
  forces a bad trade. Max steps is the Claude tool-call budget per run.

  Self-saving: lives on /settings/code which has no shared Save button,
  so this card persists changes inline through ``saveConnections``.
-->
<template>
  <v-card class="pa-5 settings-card mt-4" color="surface">
    <div class="d-flex align-center ga-3 mb-1">
      <v-avatar size="36" color="surface-variant" rounded="lg">
        <v-icon icon="mdi-timer-cog-outline" size="22" />
      </v-avatar>
      <div class="flex-grow-1">
        <div class="text-body-1 font-weight-medium">Scan tuning</div>
        <div class="text-caption text-medium-emphasis">
          Override Claude subprocess timeouts and tool-call budget. Bump these
          if synthesis or merge phases are timing out before completing.
        </div>
      </div>
    </div>

    <v-divider class="my-4" />

    <v-form ref="formRef" v-model="formValid">
      <v-row dense>
        <v-col cols="12" md="4">
          <v-text-field
            v-model.number="synthTimeout"
            :rules="timeoutRules"
            type="number"
            label="Synthesis timeout (seconds)"
            variant="outlined"
            density="compact"
            :hint="formatMinutes(synthTimeout)"
            persistent-hint
          />
        </v-col>
        <v-col cols="12" md="4">
          <v-text-field
            v-model.number="mergeTimeout"
            :rules="timeoutRules"
            type="number"
            label="Merge timeout (seconds)"
            variant="outlined"
            density="compact"
            :hint="formatMinutes(mergeTimeout)"
            persistent-hint
          />
        </v-col>
        <v-col cols="12" md="4">
          <v-text-field
            v-model.number="maxTurns"
            :rules="maxTurnsRules"
            type="number"
            label="Max steps (tool calls)"
            variant="outlined"
            density="compact"
            hint="Claude tool-call budget per run"
            persistent-hint
          />
        </v-col>
      </v-row>
    </v-form>

    <div class="d-flex align-center justify-space-between mt-3">
      <div class="text-caption text-medium-emphasis">
        <v-icon icon="mdi-information-outline" size="14" class="mr-1" />
        Synth runs once per repo (in parallel). Merge runs once across all
        synthesised features.
      </div>
      <v-btn
        color="primary"
        prepend-icon="mdi-content-save-outline"
        :loading="settingsStore.saving"
        :disabled="!formValid"
        @click="onSave"
      >
        Save
      </v-btn>
    </div>

    <v-snackbar
      v-model="savedSnackbar"
      color="success"
      timeout="2000"
      location="bottom right"
    >
      Scan tuning saved.
    </v-snackbar>
  </v-card>
</template>

<script setup lang="ts">
import { computed, ref } from 'vue'
import { useSettingsStore } from '@/stores/settings'

const settingsStore = useSettingsStore()

// Bounds mirror backend ScanSettings (Pydantic Field constraints) — keep
// in sync. The backend rejects out-of-range values with 422, so client-side
// rules are a UX hint, not the source of truth.
const TIMEOUT_MIN = 60
const TIMEOUT_MAX = 3600
const MAX_TURNS_MIN = 0
const MAX_TURNS_MAX = 100

type Rule = (v: number) => true | string

const timeoutRules: Rule[] = [
  (v) => (Number.isFinite(v) && v >= TIMEOUT_MIN && v <= TIMEOUT_MAX) ||
    `Must be between ${TIMEOUT_MIN} and ${TIMEOUT_MAX} seconds`,
]

const maxTurnsRules: Rule[] = [
  (v) => (Number.isFinite(v) && v >= MAX_TURNS_MIN && v <= MAX_TURNS_MAX) ||
    `Must be between ${MAX_TURNS_MIN} and ${MAX_TURNS_MAX}`,
]

function formatMinutes(seconds: number): string {
  if (!Number.isFinite(seconds) || seconds <= 0) return ''
  const minutes = seconds / 60
  return minutes >= 1
    ? `≈ ${minutes.toFixed(minutes % 1 === 0 ? 0 : 1)} min`
    : `${seconds}s`
}

const synthTimeout = computed<number>({
  get: () => settingsStore.connections.scan.timeoutSeconds,
  set: (v) => {
    settingsStore.connections.scan.timeoutSeconds = v
  },
})

const mergeTimeout = computed<number>({
  get: () => settingsStore.connections.scan.mergeTimeoutSeconds,
  set: (v) => {
    settingsStore.connections.scan.mergeTimeoutSeconds = v
  },
})

const maxTurns = computed<number>({
  get: () => settingsStore.connections.scan.maxTurns,
  set: (v) => {
    settingsStore.connections.scan.maxTurns = v
  },
})

const formRef = ref()
const formValid = ref(true)
const savedSnackbar = ref(false)

async function onSave(): Promise<void> {
  const ok = await settingsStore.saveConnections()
  if (ok) savedSnackbar.value = true
}
</script>
