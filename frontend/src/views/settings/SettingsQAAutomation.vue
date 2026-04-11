<template>
  <div class="settings-page">
    <!-- Header -->
    <div class="settings-header pa-6 pb-4">
      <div class="d-flex align-center justify-space-between">
        <div>
          <div class="text-h5 font-weight-bold">QA Automation & BUD Stages</div>
          <div class="text-body-2 text-medium-emphasis">
            Configure the test automation framework and BUD lifecycle stages for your organization
          </div>
        </div>
        <div class="d-flex ga-2">
          <v-btn variant="text" prepend-icon="mdi-arrow-left" :to="{ name: 'settings' }">
            Back to Settings
          </v-btn>
          <v-btn
            color="primary"
            prepend-icon="mdi-content-save-outline"
            :loading="settingsStore.saving"
            :disabled="!isValid"
            @click="save"
          >
            Save Changes
          </v-btn>
        </div>
      </div>

      <v-alert v-if="settingsStore.error" type="error" variant="tonal" class="mt-4" closable>
        {{ settingsStore.error }}
      </v-alert>
      <v-alert
        v-if="settingsStore.saveSuccess"
        type="success"
        variant="tonal"
        class="mt-4"
        closable
        @click:close="settingsStore.saveSuccess = false"
      >
        Settings saved successfully.
      </v-alert>
    </div>

    <!-- Content -->
    <div class="px-6 pb-6">
      <div v-if="settingsStore.loading" class="d-flex justify-center py-12">
        <v-progress-circular indeterminate color="primary" />
      </div>

      <template v-else>
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
          <div class="text-caption text-medium-emphasis">
            When off, BUDs transition directly from Testing to Prod. Useful for
            teams without a dedicated User Acceptance Testing phase. Existing
            BUDs currently in UAT are unaffected — only new transitions are
            blocked.
          </div>
        </v-card>
      </template>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
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
