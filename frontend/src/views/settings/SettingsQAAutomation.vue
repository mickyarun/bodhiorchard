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
  <SettingsPageShell
    title="QA Automation & BUD Stages"
    subtitle="Configure the test automation framework and BUD lifecycle stages for your organization"
    :loading="settingsStore.loading"
    :saving="settingsStore.saving"
    :valid="isValid"
    :error="settingsStore.error"
    :save-success="settingsStore.saveSuccess"
    @save="save"
    @success-close="settingsStore.saveSuccess = false"
  >
        <!-- ─── QA AUTOMATION CARD ───────────────────────────── -->
        <v-card class="pa-6 mb-6" variant="outlined">
          <div class="d-flex align-center ga-3 mb-4">
            <v-avatar size="36" color="surface-variant" rounded="lg">
              <v-icon icon="mdi-test-tube" size="22" />
            </v-avatar>
            <div>
              <div class="text-body-1 font-weight-medium">QA Automation</div>
              <div class="text-caption text-medium-emphasis">
                Controls how the QA agent generates automation test cases
              </div>
            </div>
          </div>

          <v-switch
            v-model="qa.enabled"
            label="Generate automation test cases"
            color="primary"
            hide-details
            density="compact"
            class="mb-2"
          />
          <div class="text-caption text-medium-emphasis mb-4">
            When off, the QA agent produces manual test cases only. Framework
            selection below is ignored in that mode.
          </div>

          <v-divider class="my-4" />

          <div class="text-body-2 font-weight-medium mb-2">Automation Framework</div>
          <div class="text-caption text-medium-emphasis mb-3">
            The QA agent is instructed to write test scenarios targeting this framework.
            Developers can hand the output to Claude Code to generate runnable test files.
          </div>

          <v-select
            v-model="frameworkChoice"
            :items="frameworkItems"
            label="Framework"
            variant="outlined"
            density="compact"
            hide-details
            :disabled="!qa.enabled"
            class="mb-3"
            style="max-width: 360px"
          />

          <v-text-field
            v-if="frameworkChoice === 'custom'"
            v-model="customFramework"
            label="Custom framework name"
            placeholder="e.g. WebdriverIO, TestCafe, Robot Framework"
            variant="outlined"
            density="compact"
            :rules="customFrameworkRules"
            :disabled="!qa.enabled"
            style="max-width: 360px"
          />
        </v-card>

        <!-- ─── BUD STAGES CARD ──────────────────────────────── -->
        <v-card class="pa-6 mb-6" variant="outlined">
          <div class="d-flex align-center ga-3 mb-4">
            <v-avatar size="36" color="surface-variant" rounded="lg">
              <v-icon icon="mdi-source-branch" size="22" />
            </v-avatar>
            <div>
              <div class="text-body-1 font-weight-medium">BUD Lifecycle Stages</div>
              <div class="text-caption text-medium-emphasis">
                Toggle optional stages in your BUD workflow
              </div>
            </div>
          </div>

          <v-switch
            v-model="budStages.uatEnabled"
            label="Include UAT stage"
            color="primary"
            hide-details
            density="compact"
            class="mb-2"
          />
          <div class="text-caption text-medium-emphasis mb-6">
            When off, BUDs transition directly from Testing to Prod. Useful for
            teams without a dedicated User Acceptance Testing phase. Existing
            BUDs currently in UAT are unaffected — only new transitions are
            blocked.
          </div>

          <v-divider class="mb-4" />

          <div class="d-flex align-center mb-3">
            <div>
              <div class="text-body-1 font-weight-medium">Bug Rejection Threshold</div>
              <div class="text-caption text-medium-emphasis">
                When open bugs on a BUD in testing reach this count, the BUD is
                automatically sent back to development and the QA tester is freed.
              </div>
            </div>
          </div>

          <v-text-field
            v-model.number="qa.bugRejectThreshold"
            type="number"
            label="Max open bugs before rejection"
            variant="outlined"
            density="compact"
            :min="1"
            :max="50"
            style="max-width: 200px"
            hide-details
          />
        </v-card>
  </SettingsPageShell>
</template>

<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import SettingsPageShell from '@/components/settings/SettingsPageShell.vue'
import { useSettingsStore } from '@/stores/settings'

const settingsStore = useSettingsStore()

// Two-way bindings against the store's reactive connections object. Mutating
// these writes back through the store and is persisted by saveConnections().
const qa = computed(() => settingsStore.connections.qaAutomation)
const budStages = computed(() => settingsStore.connections.budStages)

// Built-in framework list. "custom" opens a free-text field constrained to
// the same regex the backend uses in QAAutomationSettings — keeps UX and
// validation honest even when offline.
const BUILTIN_FRAMEWORKS = ['playwright', 'selenium', 'cypress', 'cucumber'] as const
type BuiltinFramework = (typeof BUILTIN_FRAMEWORKS)[number]

const frameworkItems = [
  { title: 'Playwright', value: 'playwright' },
  { title: 'Selenium', value: 'selenium' },
  { title: 'Cypress', value: 'cypress' },
  { title: 'Cucumber', value: 'cucumber' },
  { title: 'Custom…', value: 'custom' },
]

// Mirror regex of backend QAAutomationSettings.framework. See
// backend/app/schemas/settings.py — keep in sync.
const FRAMEWORK_REGEX = /^[a-zA-Z0-9 _+\-]{1,40}$/

const customFrameworkRules = [
  (v: string) => !!v || 'Required when Custom is selected',
  (v: string) =>
    FRAMEWORK_REGEX.test(v) ||
    'Only letters, digits, space, underscore, plus, and hyphen allowed (max 40 chars)',
]

// ──────────────────────────────────────────────────────────────
// Framework select ⇄ store value bridging
//
// The store keeps a single `framework` string. The UI splits that into
// "builtin choice + custom text" so the Custom flow needs a dedicated
// text field. When the user picks a builtin, we write it straight to
// the store. When they pick Custom, we write the custom text instead.
// ──────────────────────────────────────────────────────────────

const frameworkChoice = ref<BuiltinFramework | 'custom'>('playwright')
const customFramework = ref('')

function syncChoiceFromStore(): void {
  const stored = qa.value.framework
  if ((BUILTIN_FRAMEWORKS as readonly string[]).includes(stored)) {
    frameworkChoice.value = stored as BuiltinFramework
    customFramework.value = ''
  } else {
    frameworkChoice.value = 'custom'
    customFramework.value = stored
  }
}

watch(
  () => qa.value.framework,
  () => syncChoiceFromStore(),
  { immediate: false },
)

watch(frameworkChoice, (choice) => {
  if (choice !== 'custom') {
    qa.value.framework = choice
  } else if (customFramework.value) {
    qa.value.framework = customFramework.value
  }
})

watch(customFramework, (value) => {
  if (frameworkChoice.value === 'custom' && FRAMEWORK_REGEX.test(value)) {
    qa.value.framework = value
  }
})

// Save is disabled when custom framework input is invalid — prevents the
// PATCH from being rejected with a 422 the user can't easily debug.
const isValid = computed(() => {
  if (frameworkChoice.value === 'custom') {
    return FRAMEWORK_REGEX.test(customFramework.value)
  }
  return true
})

async function save(): Promise<void> {
  await settingsStore.saveConnections()
}

onMounted(async () => {
  if (!settingsStore.connections.qaAutomation) {
    await settingsStore.fetchConnections()
  }
  syncChoiceFromStore()
})
</script>
