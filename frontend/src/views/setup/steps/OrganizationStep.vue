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
  <SetupStepHeader
    :step="1"
    title="Name your workspace"
    description="This is the organization your team signs in to. You can rename it later in Settings."
  />
  <v-card class="pa-6 card-border-dark" color="surface">
    <v-text-field
      v-model="setupStore.state.organization.name"
      label="Organization name"
      placeholder="Acme Inc."
      prepend-inner-icon="mdi-office-building-outline"
      class="mb-4"
      :rules="[rules.required]"
      :readonly="setupStore.orgInitDone"
      :hint="setupStore.orgInitDone ? lockedHint : undefined"
      :persistent-hint="setupStore.orgInitDone"
      @update:model-value="onNameChange"
    />

    <v-text-field
      v-model="setupStore.state.organization.slug"
      label="URL slug"
      placeholder="acme-inc"
      prepend-inner-icon="mdi-link-variant"
      :hint="setupStore.orgInitDone ? lockedHint : 'Used in URLs. Lowercase letters, numbers, and hyphens only.'"
      persistent-hint
      class="mb-4"
      :rules="[rules.required, rules.slug]"
      :readonly="setupStore.orgInitDone"
    />

    <AppCallout variant="info">
      You can add more organizations later.
    </AppCallout>
  </v-card>
</template>

<script setup lang="ts">
import AppCallout from '@/components/common/AppCallout.vue'
import SetupStepHeader from '@/components/setup/SetupStepHeader.vue'
import { useSetupStore } from '@/stores/setup'

const setupStore = useSetupStore()

// Once submitOrgInit succeeds, the org row exists in the
// backend and these fields can no longer be changed (the wizard's
// "create org" trigger has already fired). Reads cleanly as read-only
// instead of throwing on the next attempt.
const lockedHint = 'Locked after Continue — the org has been created.'

const rules = {
  required: (v: string) => !!v?.trim() || 'This field is required',
  slug: (v: string) =>
    /^[a-z0-9][a-z0-9-]*$/.test(v) || 'Only lowercase letters, numbers, and hyphens',
}

function onNameChange(value: string | null): void {
  if (value) {
    setupStore.state.organization.slug = setupStore.generateSlug(value)
  }
}
</script>
