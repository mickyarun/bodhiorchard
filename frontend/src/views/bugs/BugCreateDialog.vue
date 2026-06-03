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
  <v-dialog :model-value="modelValue" max-width="540" @update:model-value="$emit('update:modelValue', $event)">
    <v-card color="surface" class="pa-6">
      <div class="text-h6 font-weight-bold mb-4">Report a Bug</div>

      <v-text-field
        v-model="title"
        label="Title *"
        variant="outlined"
        density="compact"
        class="mb-3"
        :rules="[v => !!v?.trim() || 'Title is required']"
      />

      <v-textarea
        v-model="description"
        label="Description"
        variant="outlined"
        density="compact"
        rows="3"
        class="mb-3"
        placeholder="Steps to reproduce, expected vs actual behavior..."
      />

      <div class="d-flex ga-3 mb-3">
        <v-select
          v-model="severity"
          :items="severityOptions"
          label="Severity"
          variant="outlined"
          density="compact"
          style="flex: 1"
        />
        <v-text-field
          v-model="module"
          label="Module / Area"
          variant="outlined"
          density="compact"
          style="flex: 1"
          placeholder="e.g. payments, auth"
        />
      </div>

      <!-- BUD link path: only shown when the dialog is opened from a
        BUD context (BUDBugsPanel passes ``budId``). The parent BUD
        view already shows the formatted ``BUD-NNN`` number, so we
        just acknowledge the link inline. -->
      <div v-if="budId" class="text-caption text-medium-emphasis mb-3">
        This bug will be linked to the current BUD.
      </div>

      <!-- Feature picker — production-bug surface only. -->
      <template v-else-if="resolvedBugType === 'production'">
        <v-autocomplete
          v-model="selectedFeatureId"
          :items="featureOptions"
          :loading="featureLoading"
          item-title="label"
          item-value="value"
          label="Link to Feature (optional)"
          variant="outlined"
          density="compact"
          placeholder="Search features…"
          hint="AI auto-detects the closest Feature when left empty."
          persistent-hint
          clearable
          class="mb-3"
          @update:search="onFeatureSearch"
        />
      </template>

      <v-card-actions class="pa-0 mt-4">
        <v-spacer />
        <v-btn variant="text" @click="$emit('update:modelValue', false)">Cancel</v-btn>
        <v-btn
          color="error"
          variant="flat"
          :disabled="!title?.trim()"
          :loading="saving"
          @click="submit"
        >
          Report Bug
        </v-btn>
      </v-card-actions>
    </v-card>
  </v-dialog>
</template>

<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { useBugsStore } from '@/stores/bugs'
import { useFeaturesStore } from '@/stores/features'
import type { BugRead } from '@/types'

const props = defineProps<{
  modelValue: boolean
  budId?: string | null
  defaultBugType?: 'testing' | 'production'
}>()

const emit = defineEmits<{
  (e: 'update:modelValue', value: boolean): void
  (e: 'created', bug: BugRead): void
}>()

const bugsStore = useBugsStore()
const featuresStore = useFeaturesStore()

const title = ref('')
const description = ref('')
const severity = ref('medium')
const module = ref('')
const selectedFeatureId = ref<string | null>(null)
const featureLoading = ref(false)
const saving = ref(false)
let featureSearchTimer: ReturnType<typeof setTimeout> | null = null

const severityOptions = [
  { title: 'Low', value: 'low' },
  { title: 'Medium', value: 'medium' },
  { title: 'High', value: 'high' },
  { title: 'Critical', value: 'critical' },
]

// When opened from a BUD detail panel the bug is by definition a
// testing bug; otherwise inherit the board's current scope (production
// is the /bugs page default).
const resolvedBugType = computed(() => {
  if (props.budId) return 'testing'
  return props.defaultBugType ?? 'production'
})

const featureOptions = computed(() =>
  featuresStore.items.map((f) => ({
    label: f.featureTitle,
    value: f.id,
  })),
)

watch(
  () => props.modelValue,
  async (open) => {
    if (!open) return
    if (!props.budId && featuresStore.items.length === 0) {
      featureLoading.value = true
      await featuresStore.fetchPage({ mode: 'active' })
      featureLoading.value = false
    }
  },
)

function onFeatureSearch(query: string): void {
  if (featureSearchTimer) clearTimeout(featureSearchTimer)
  featureSearchTimer = setTimeout(async () => {
    featureLoading.value = true
    await featuresStore.fetchPage({ q: query || undefined, mode: 'active' })
    featureLoading.value = false
  }, 250)
}

async function submit(): Promise<void> {
  if (!title.value.trim()) return
  saving.value = true
  const bug = await bugsStore.createBug({
    title: title.value.trim(),
    description: description.value.trim() || undefined,
    severity: severity.value,
    module: module.value.trim() || undefined,
    budId: props.budId || undefined,
    featureId: !props.budId ? selectedFeatureId.value || undefined : undefined,
    bugType: !props.budId ? resolvedBugType.value : undefined,
  })
  saving.value = false
  if (bug) {
    title.value = ''
    description.value = ''
    severity.value = 'medium'
    module.value = ''
    selectedFeatureId.value = null
    emit('update:modelValue', false)
    emit('created', bug)
  }
}
</script>
