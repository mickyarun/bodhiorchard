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
  <v-dialog
    :model-value="modelValue"
    max-width="640"
    @update:model-value="emit('update:modelValue', $event)"
  >
    <v-card>
      <v-card-title class="d-flex align-center">
        <span>Link existing features</span>
        <v-spacer />
        <v-btn icon="mdi-close" variant="text" size="small" @click="close" />
      </v-card-title>

      <v-card-text class="pt-2">
        <v-text-field
          v-model="query"
          density="compact"
          variant="outlined"
          placeholder="Search features by title…"
          prepend-inner-icon="mdi-magnify"
          hide-details
          autofocus
          clearable
          @update:model-value="onQueryChange"
        />

        <div class="mt-3" style="min-height: 240px; max-height: 360px; overflow-y: auto;">
          <div v-if="searching" class="d-flex justify-center py-6">
            <v-progress-circular indeterminate size="24" color="teal" />
          </div>

          <div v-else-if="results.length === 0" class="text-body-2 text-medium-emphasis py-4 text-center">
            {{ query ? 'No features match' : 'Start typing to search' }}
          </div>

          <v-list v-else density="compact" select-strategy="leaf" :selected="selectedIds" @update:selected="onSelectionChange">
            <v-list-item
              v-for="feature in results"
              :key="feature.id"
              :value="feature.id"
              :disabled="alreadyLinked(feature.id)"
              :title="alreadyLinked(feature.id) ? 'Already linked' : undefined"
            >
              <template #prepend="{ isSelected }">
                <v-checkbox-btn :model-value="isSelected" :disabled="alreadyLinked(feature.id)" />
              </template>
              <v-list-item-title class="text-body-2">
                {{ feature.featureTitle }}
                <span v-if="alreadyLinked(feature.id)" class="text-caption text-medium-emphasis ml-2">
                  (already linked)
                </span>
              </v-list-item-title>
              <v-list-item-subtitle v-if="feature.primary?.repoName">
                {{ feature.primary.repoName }}
              </v-list-item-subtitle>
            </v-list-item>
          </v-list>
        </div>

        <v-alert v-if="errorText" type="error" variant="tonal" density="compact" class="mt-2">
          {{ errorText }}
        </v-alert>
      </v-card-text>

      <v-card-actions>
        <v-spacer />
        <v-btn variant="text" @click="close">Cancel</v-btn>
        <v-btn
          color="teal"
          variant="flat"
          :disabled="selectedIds.length === 0 || submitting"
          :loading="submitting"
          @click="onAdd"
        >
          Add {{ selectedIds.length || '' }} selected
        </v-btn>
      </v-card-actions>
    </v-card>
  </v-dialog>
</template>

<script setup lang="ts">
import { ref, watch } from 'vue'
import api from '@/services/api'
import type { Feature, FeaturePage } from '@/types'
import { useBudLinkedFeaturesStore } from '@/stores/budLinkedFeatures'
import { extractApiError } from '@/utils/errors'

const props = defineProps<{
  modelValue: boolean
  budId: string
  existingIds: string[]
}>()
const emit = defineEmits<{
  'update:modelValue': [value: boolean]
  linked: [insertedCount: number]
}>()

const store = useBudLinkedFeaturesStore()

const query = ref('')
const results = ref<Feature[]>([])
const selectedIds = ref<string[]>([])
const searching = ref(false)
const submitting = ref(false)
const errorText = ref('')

let debounceTimer: ReturnType<typeof setTimeout> | null = null

function alreadyLinked(id: string): boolean {
  return props.existingIds.includes(id)
}

function onSelectionChange(ids: unknown[]) {
  // v-list emits string[] for our values; cast defensively.
  selectedIds.value = (ids as string[]).filter(id => !alreadyLinked(id))
}

function onQueryChange(_value: string | null) {
  if (debounceTimer) clearTimeout(debounceTimer)
  debounceTimer = setTimeout(() => void runSearch(), 250)
}

async function runSearch() {
  errorText.value = ''
  const q = (query.value ?? '').trim()
  if (!q) {
    // Don't hit the API on an empty query — the empty-state template
    // already prompts "Start typing to search".
    results.value = []
    searching.value = false
    return
  }
  searching.value = true
  try {
    const { data } = await api.get<FeaturePage>('/v1/features', {
      params: { q, limit: 20 },
    })
    results.value = data.items ?? []
  } catch (err) {
    errorText.value = extractApiError(err, 'Failed to search features')
    results.value = []
  } finally {
    searching.value = false
  }
}

async function onAdd() {
  if (selectedIds.value.length === 0) return
  submitting.value = true
  errorText.value = ''
  const resp = await store.link(props.budId, selectedIds.value)
  submitting.value = false
  if (resp) {
    emit('linked', resp.insertedCount)
    close()
  } else {
    errorText.value = store.error || 'Failed to link features'
  }
}

function close() {
  emit('update:modelValue', false)
}

function resetState() {
  query.value = ''
  results.value = []
  selectedIds.value = []
  errorText.value = ''
}

watch(
  () => props.modelValue,
  open => {
    if (open) resetState()
    // No initial fetch — the empty-state copy ("Start typing to search")
    // sets the expectation; fetching the first 20 features on open would
    // contradict it and add latency for a list the user will discard.
  },
)
</script>
