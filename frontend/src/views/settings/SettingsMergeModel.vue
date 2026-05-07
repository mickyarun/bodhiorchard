<!--
  SPDX-License-Identifier: AGPL-3.0-or-later
  Copyright (C) 2026 Arun Rajkumar

  Per-org override for the cross-repo feature merge model. Two dropdowns —
  one for the typical-scale call (≤ merge_sonnet_quality_budget features),
  one for the escalation path. ``null`` ⇒ "use platform default" so the
  org doesn't pin a specific model unless they want to.
-->
<template>
  <v-card class="pa-5 settings-card mt-4" color="surface">
    <div class="d-flex align-center ga-3 mb-1">
      <v-avatar size="36" color="surface-variant" rounded="lg">
        <v-icon icon="mdi-merge" size="22" />
      </v-avatar>
      <div class="flex-grow-1">
        <div class="text-body-1 font-weight-medium">Cross-repo merge model</div>
        <div class="text-caption text-medium-emphasis">
          Override the model used for cross-repo feature consolidation. Leave on
          <em>Use platform default</em> unless you have a specific cost / quality preference.
        </div>
      </div>
    </div>

    <v-divider class="my-4" />

    <v-row dense>
      <v-col cols="12" md="6">
        <v-select
          v-model="mergeModelDefault"
          :items="mergeModelOptions"
          label="Small batches (≤3000 features)"
          variant="outlined"
          density="compact"
          hide-details
          item-title="label"
          item-value="value"
        />
      </v-col>
      <v-col cols="12" md="6">
        <v-select
          v-model="mergeModelLarge"
          :items="mergeModelOptions"
          label="Large batches (>3000 features)"
          variant="outlined"
          density="compact"
          hide-details
          item-title="label"
          item-value="value"
        />
      </v-col>
    </v-row>

    <div class="text-caption text-medium-emphasis mt-3">
      <v-icon icon="mdi-information-outline" size="14" class="mr-1" />
      At your current scale (well below 3000 features), only the small-batch
      model runs. The large-batch model is dormant until you cross the threshold.
    </div>
  </v-card>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { useSettingsStore } from '@/stores/settings'

const settingsStore = useSettingsStore()

interface MergeModelOption {
  label: string
  value: string | null
}

// Allowlist mirrors backend get_merge_models — keep in sync. Platform
// default sentinel uses ``null`` so partial overrides round-trip cleanly
// (only the field that's set ships to the backend).
const mergeModelOptions: ReadonlyArray<MergeModelOption> = [
  { label: 'Use platform default', value: null },
  { label: 'Claude Sonnet 4.6 (faster, cheaper)', value: 'claude-sonnet-4-6' },
  { label: 'Claude Opus 4.7 (higher quality)', value: 'claude-opus-4-7' },
]

const mergeModelDefault = computed<string | null>({
  get: () => settingsStore.connections.aiConfig.mergeModelDefault,
  set: (v) => {
    settingsStore.connections.aiConfig.mergeModelDefault = v
  },
})

const mergeModelLarge = computed<string | null>({
  get: () => settingsStore.connections.aiConfig.mergeModelLarge,
  set: (v) => {
    settingsStore.connections.aiConfig.mergeModelLarge = v
  },
})
</script>
