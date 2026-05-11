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
  <v-card class="pa-8 card-border-dark" color="surface">
    <div class="d-flex align-center ga-3 mb-6">
      <v-avatar color="primary" size="44">
        <v-icon icon="mdi-domain" size="24" />
      </v-avatar>
      <div>
        <div class="text-h5 font-weight-bold">Organization</div>
        <div class="text-body-2 text-medium-emphasis">Set up your workspace</div>
      </div>
    </div>

    <v-text-field
      v-model="setupStore.state.organization.name"
      label="Organization Name"
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
      label="Slug"
      placeholder="acme-inc"
      prepend-inner-icon="mdi-link-variant"
      :hint="setupStore.orgInitDone ? lockedHint : 'Used in URLs. Lowercase letters, numbers, and hyphens only.'"
      persistent-hint
      class="mb-4"
      :rules="[rules.required, rules.slug]"
      :readonly="setupStore.orgInitDone"
    />

    <v-alert
      type="info"
      variant="tonal"
      density="compact"
      icon="mdi-information-outline"
    >
      Bodhiorchard supports multi-org setups. You can add more organizations later.
    </v-alert>
  </v-card>
</template>

<script setup lang="ts">
import { useSetupStore } from '@/stores/setup'

const setupStore = useSetupStore()

// Phase J — once submitOrgInit succeeds, the org row exists in the
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
