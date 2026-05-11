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
  Modal that edits the main / develop / UAT branch mapping for one
  repository. State + persistence live in useRepoBranches; this file
  is the presentation layer only.
-->
<template>
  <v-dialog
    :model-value="visible"
    max-width="480"
    persistent
    @update:model-value="onUpdateVisible"
  >
    <v-card v-if="branches.editing.value" color="surface">
      <v-card-title class="d-flex align-center ga-2 py-3">
        <v-icon icon="mdi-source-branch-edit" size="20" />
        <span class="text-body-1 font-weight-medium">
          Branch mapping · {{ branches.editing.value.name }}
        </span>
      </v-card-title>

      <v-divider />

      <div class="pa-5">
        <div class="text-caption text-medium-emphasis mb-4">
          Bodhiorchard ties BUDs to branches: features merge from develop,
          stage-progress reads main, and (optionally) UAT promotion follows
          a third branch or pattern.
        </div>

        <v-alert
          v-if="branches.error.value"
          type="error"
          variant="tonal"
          density="compact"
          class="mb-4"
        >
          {{ branches.error.value }}
        </v-alert>

        <div v-if="branches.loading.value" class="d-flex justify-center py-6">
          <v-progress-circular indeterminate color="primary" size="32" />
        </div>

        <template v-else>
          <v-select
            v-model="mainBranchModel"
            :items="branches.branches.value"
            label="Main branch"
            variant="outlined"
            density="compact"
            prepend-inner-icon="mdi-source-branch"
            class="mb-3"
            :disabled="branches.saving.value"
          />
          <v-select
            v-model="developBranchModel"
            :items="branches.branches.value"
            label="Develop branch"
            variant="outlined"
            density="compact"
            prepend-inner-icon="mdi-source-branch"
            class="mb-3"
            :disabled="branches.saving.value"
          />
          <v-combobox
            v-if="uatEnabled"
            v-model="uatBranchModel"
            :items="branches.branches.value"
            label="UAT branch (optional)"
            variant="outlined"
            density="compact"
            prepend-inner-icon="mdi-source-branch"
            clearable
            :disabled="branches.saving.value"
            hint="Pick a branch or type a pattern (e.g. release/uat, release*). Leave empty to skip UAT tracking."
            persistent-hint
          />
        </template>
      </div>

      <v-divider />

      <v-card-actions class="pa-4">
        <v-spacer />
        <v-btn
          variant="text"
          class="text-none"
          :disabled="branches.saving.value"
          @click="emit('close')"
        >
          Cancel
        </v-btn>
        <v-btn
          color="primary"
          variant="flat"
          class="text-none"
          :disabled="!canSave"
          :loading="branches.saving.value"
          @click="onSave"
        >
          Save
        </v-btn>
      </v-card-actions>
    </v-card>
  </v-dialog>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { useSettingsStore } from '@/stores/settings'
import type { useRepoBranches } from '@/composables/useRepoBranches'

const props = defineProps<{
  branches: ReturnType<typeof useRepoBranches>
}>()

const emit = defineEmits<{
  close: []
  saved: []
}>()

const settingsStore = useSettingsStore()

const visible = computed(() => props.branches.editing.value !== null)
const uatEnabled = computed(
  () => settingsStore.connections.budStages?.uatEnabled ?? true,
)

const mainBranchModel = computed({
  get: () => props.branches.mainBranch.value,
  set: (v) => { props.branches.mainBranch.value = v },
})
const developBranchModel = computed({
  get: () => props.branches.developBranch.value,
  set: (v) => { props.branches.developBranch.value = v },
})
const uatBranchModel = computed({
  get: () => props.branches.uatBranch.value,
  set: (v) => { props.branches.uatBranch.value = v },
})

const canSave = computed(() =>
  !!props.branches.mainBranch.value
  && !!props.branches.developBranch.value
  && !props.branches.saving.value,
)

function onUpdateVisible(v: boolean): void {
  if (!v) emit('close')
}

async function onSave(): Promise<void> {
  const ok = await props.branches.save()
  if (ok) {
    emit('saved')
    emit('close')
  }
}
</script>
