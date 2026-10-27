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
  <div>
    <SetupStepHeader
      :step="5"
      title="Ready to launch"
      description="Your workspace is set up and the first scan has started. You can change any of this later in Settings."
    />

    <section class="review-step__card" aria-label="Setup summary">
      <div v-for="row in summary" :key="row.label" class="review-step__row">
        <div class="review-step__label">{{ row.label }}</div>
        <div class="review-step__value">
          <template v-if="row.lines.length">
            <span v-for="(line, i) in row.lines" :key="i" class="review-step__line">{{ line }}</span>
          </template>
          <span v-else class="review-step__empty">Not set</span>
        </div>
      </div>
    </section>

    <AppCallout variant="info" class="mb-6">
      Cloning and the first scan run in the background, with live progress on the dashboard.
      You can connect GitHub, Slack and other tools from Settings while it runs.
    </AppCallout>

    <v-btn
      color="primary"
      size="large"
      prepend-icon="mdi-rocket-launch-outline"
      :loading="setupStore.isSubmitting"
      @click="emit('launch')"
    >
      Launch Glideship
    </v-btn>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import AppCallout from '@/components/common/AppCallout.vue'
import SetupStepHeader from '@/components/setup/SetupStepHeader.vue'
import { providerTitle } from '@/constants/aiProviders'
import { useSetupStore } from '@/stores/setup'

const setupStore = useSetupStore()

const emit = defineEmits<{
  launch: []
}>()

interface SummaryRow {
  label: string
  lines: string[]
}

const summary = computed<SummaryRow[]>(() => {
  const { organization, admin, claude, sourceCode } = setupStore.state
  const repoLines = sourceCode.repos.map(
    (r) => `${r.path.split('/').pop()} · ${r.mainBranch || '?'} / ${r.developBranch || '?'}`,
  )
  return [
    { label: 'Organization', lines: [organization.name, organization.slug].filter(Boolean) },
    { label: 'Admin', lines: [admin.name, admin.email].filter(Boolean) },
    { label: 'AI engine', lines: [providerTitle(claude.provider)] },
    { label: 'Repositories', lines: repoLines },
  ]
})
</script>

<style scoped>
.review-step__card {
  margin-bottom: var(--space-md, 1.5rem);
  border: 1px solid rgb(var(--v-theme-rule));
  border-radius: var(--radius-card, 10px);
  background: rgb(var(--v-theme-surface));
}

.review-step__row {
  display: grid;
  grid-template-columns: 140px minmax(0, 1fr);
  gap: var(--space-sm, 1rem);
  align-items: start;
  padding: 16px 20px;
}

.review-step__row + .review-step__row {
  border-top: 1px solid rgb(var(--v-theme-rule));
}

.review-step__label {
  padding-top: 6px;
  font-size: 14px;
  color: rgb(var(--v-theme-muted));
}

.review-step__value {
  padding-top: 6px;
  display: flex;
  flex-direction: column;
  gap: 2px;
  min-width: 0;
  font-size: 14px;
  color: rgb(var(--v-theme-on-surface));
}

.review-step__line {
  overflow-wrap: anywhere;
}

.review-step__empty {
  color: rgb(var(--v-theme-muted));
}

/* Phones: label above value. */
@media (max-width: 599px) {
  .review-step__row {
    grid-template-columns: minmax(0, 1fr);
    row-gap: 2px;
  }

  .review-step__value {
    padding-top: 0;
  }
}
</style>
