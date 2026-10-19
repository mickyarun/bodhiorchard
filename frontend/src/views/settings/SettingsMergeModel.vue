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
          :items="defaultOptions"
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
          :items="largeOptions"
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
import { computed, onMounted, ref } from 'vue'
import api from '@/services/api'
import type { MergeModelChoice } from '@/constants/aiProviders'
import { useSettingsStore } from '@/stores/settings'

const settingsStore = useSettingsStore()

interface MergeModelOption {
  label: string
  value: string | null
}

// ``null`` ⇒ "use platform default", so a partial override round-trips
// cleanly: only the field that is actually set ships to the backend.
const PLATFORM_DEFAULT: MergeModelOption = { label: 'Use platform default', value: null }

// Served by the capabilities endpoint, not listed here. The copy this replaced
// kept its own allowlist behind a "keep in sync" comment, and by the time
// anyone read it the dropdown was offering two models that had each been
// superseded by a newer release at the same price or less. The backend also
// decides which tiers belong in a merge setting, so this can no longer offer
// a model that `get_merge_models` would discard on read.
const choices = ref<MergeModelChoice[]>([])

onMounted(async () => {
  try {
    const { data } = await api.get('/v1/settings/ai/capabilities')
    choices.value = data.merge_models ?? []
  } catch (err: unknown) {
    const axiosErr = err as { response?: { status?: number } }
    if (axiosErr?.response?.status !== 401) {
      console.warn('[SettingsMergeModel] failed to load the merge model choices', err)
    }
  }
})

function describe(model: MergeModelChoice): MergeModelOption {
  return { label: `${model.label} — ${model.price_label}`, value: model.id }
}

/**
 * Platform default plus every model the backend offers — and whatever the org
 * has actually pinned, when that is something else.
 *
 * The backend still honours a pin on a model it no longer offers, so dropping
 * it from the list would render the select blank and rewrite a deliberate
 * choice on the next save. Same for the moment before the choices load.
 */
function optionsFor(selected: string | null): MergeModelOption[] {
  const options = [PLATFORM_DEFAULT, ...choices.value.filter(m => m.offered).map(describe)]
  if (selected === null || options.some(o => o.value === selected)) return options
  const known = choices.value.find(m => m.id === selected)
  return [...options, known ? describe(known) : { label: selected, value: selected }]
}

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

const defaultOptions = computed(() => optionsFor(mergeModelDefault.value))
const largeOptions = computed(() => optionsFor(mergeModelLarge.value))
</script>
