<!--
  Copyright 2025-2026 Arun Rajkumar

  Licensed under the Apache License, Version 2.0 (the "License");
  you may not use this file except in compliance with the License.
  You may obtain a copy of the License at

      http://www.apache.org/licenses/LICENSE-2.0

  Unless required by applicable law or agreed to in writing, software
  distributed under the License is distributed on an "AS IS" BASIS,
  WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
  See the License for the specific language governing permissions and
  limitations under the License.
-->
<!-- Admin configuration for the Company Quiz Game. -->
<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'

import AppCallout from '@/components/common/AppCallout.vue'
import AppPillToggle from '@/components/common/AppPillToggle.vue'
import SettingsPageShell from '@/components/settings/SettingsPageShell.vue'
import { useQuizReviewStore } from '@/stores/quizReview'
import type { QuizDifficulty, QuizSettings } from '@/types/quiz'

const store = useQuizReviewStore()
const saveSuccess = ref(false)

const WEEKDAYS = [
  { title: 'Mon', value: 0 },
  { title: 'Tue', value: 1 },
  { title: 'Wed', value: 2 },
  { title: 'Thu', value: 3 },
  { title: 'Fri', value: 4 },
  { title: 'Sat', value: 5 },
  { title: 'Sun', value: 6 },
]
const DIFFICULTIES: { label: string; value: QuizDifficulty }[] = [
  { label: 'Easy', value: 'easy' },
  { label: 'Medium', value: 'medium' },
  { label: 'Hard', value: 'hard' },
  { label: 'Mixed', value: 'mixed' },
]
const TYPES = [
  { title: 'Multiple choice', value: 'multiple_choice' },
  { title: 'Scramble', value: 'scramble' },
  { title: 'Fill in the blank', value: 'fill_blank' },
]

function timezones(): string[] {
  try {
    return (Intl as unknown as { supportedValuesOf: (k: string) => string[] }).supportedValuesOf(
      'timeZone'
    )
  } catch {
    return []
  }
}

const form = ref<QuizSettings | null>(null)

const valid = computed(
  () =>
    !!form.value &&
    form.value.activeWeekdays.length > 0 &&
    form.value.enabledQuestionTypes.length > 0
)

async function load(): Promise<void> {
  await store.fetchSettings()
  if (store.settings) form.value = { ...store.settings }
}

async function save(): Promise<void> {
  if (!form.value || !valid.value) return
  if (await store.saveSettings(form.value)) saveSuccess.value = true
}

onMounted(load)
</script>

<template>
  <SettingsPageShell
    title="Quiz Game"
    subtitle="A daily knowledge game built from your own dev data."
    :loading="store.loading"
    :saving="store.saving"
    :valid="valid"
    :error="store.error || null"
    :save-success="saveSuccess"
    @save="save"
    @success-close="saveSuccess = false"
  >
    <AppCallout
      variant="info"
      eyebrow="How it works"
      icon="mdi-shield-check-outline"
      class="mb-6"
    >
      The AI drafts questions ahead of time; you approve them in Review before they go live. No XP
      is ever awarded — the top monthly scorer earns SP.
    </AppCallout>

    <template v-if="form">
      <v-switch
        v-model="form.enabled"
        color="primary"
        label="Enable the company quiz"
        hide-details
        class="mb-4"
      />

      <v-select
        v-model="form.activeWeekdays"
        :items="WEEKDAYS"
        label="Quiz days"
        multiple
        chips
        variant="outlined"
        density="comfortable"
        class="mb-4"
      />

      <div class="d-flex ga-4 mb-4 flex-wrap">
        <v-text-field
          v-model="form.quizTime"
          type="time"
          label="Open time"
          variant="outlined"
          density="comfortable"
          style="max-width: 180px"
          hide-details
        />
        <v-autocomplete
          v-model="form.timezone"
          :items="timezones()"
          label="Timezone (blank = server)"
          clearable
          variant="outlined"
          density="comfortable"
          style="min-width: 260px"
          hide-details
        />
      </div>

      <div class="d-flex ga-4 mb-4 flex-wrap">
        <v-text-field
          v-model.number="form.windowMinutes"
          type="number"
          label="Open window (min)"
          variant="outlined"
          density="comfortable"
          style="max-width: 200px"
          hide-details
        />
        <v-text-field
          v-model.number="form.speedGraceMinutes"
          type="number"
          label="Speed-bonus grace (min)"
          variant="outlined"
          density="comfortable"
          style="max-width: 220px"
          hide-details
        />
      </div>

      <div class="mb-2 text-body-2 text-medium-emphasis">Difficulty</div>
      <AppPillToggle v-model="form.difficulty" :options="DIFFICULTIES" class="mb-4" />

      <v-select
        v-model="form.enabledQuestionTypes"
        :items="TYPES"
        label="Question types in rotation"
        multiple
        chips
        variant="outlined"
        density="comfortable"
        class="mb-4"
      />

      <v-text-field
        v-model.number="form.monthlySpAmount"
        type="number"
        step="0.5"
        label="Monthly champion SP"
        variant="outlined"
        density="comfortable"
        style="max-width: 220px"
        class="mb-4"
        hide-details
      />

      <v-switch
        v-model="form.slackNotifyOpen"
        color="primary"
        label="Slack DM members when a quiz opens"
        hide-details
      />
      <v-switch
        v-model="form.slackNotifyReveal"
        color="primary"
        label="Slack DM members at reveal"
        hide-details
      />
    </template>

    <template #header-actions>
      <v-btn variant="tonal" to="/settings/quiz-review" prepend-icon="mdi-clipboard-check-outline">
        Review questions
      </v-btn>
    </template>
  </SettingsPageShell>
</template>
