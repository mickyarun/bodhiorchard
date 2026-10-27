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

<!-- Picks the live feature a bug belongs to. Searching asks the server
     (debounced); the first page loads on mount. ``currentTitle`` keeps an
     already-linked feature named before any search has found it. -->
<template>
  <v-autocomplete
    :model-value="modelValue"
    :items="options"
    :loading="loading"
    :label="label"
    :hint="hint"
    :persistent-hint="!!hint"
    :hide-details="!hint"
    placeholder="Search features"
    persistent-placeholder
    no-filter
    variant="outlined"
    density="compact"
    clearable
    @update:search="onSearch"
    @update:model-value="emit('update:modelValue', $event ?? null)"
  />
</template>

<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import { SEARCH_DELAY_MS } from '@/composables/useDebounced'
import { useFeaturesStore } from '@/stores/features'

const props = withDefaults(
  defineProps<{ modelValue: string | null; label?: string; hint?: string; currentTitle?: string | null }>(),
  { label: 'Feature', hint: undefined, currentTitle: null },
)
const emit = defineEmits<{ 'update:modelValue': [featureId: string | null] }>()

const featuresStore = useFeaturesStore()
const loading = ref(false)
let timer: ReturnType<typeof setTimeout> | undefined

const options = computed(() => {
  const list = featuresStore.items.map(f => ({ title: f.featureTitle, value: f.id }))
  if (props.modelValue && props.currentTitle && !list.some(o => o.value === props.modelValue)) {
    list.unshift({ title: props.currentTitle, value: props.modelValue })
  }
  return list
})

async function search(q?: string): Promise<void> {
  loading.value = true
  await featuresStore.fetchPage({ q, mode: 'active' })
  loading.value = false
}

function onSearch(query: string): void {
  clearTimeout(timer)
  timer = setTimeout(() => void search(query || undefined), SEARCH_DELAY_MS)
}

onMounted(() => {
  if (featuresStore.items.length === 0) void search()
})
onBeforeUnmount(() => clearTimeout(timer))
</script>
