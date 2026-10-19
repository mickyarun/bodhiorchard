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

<!-- Country and region for a policy; the region list follows the
     country. Public holidays are imported for this pair. -->
<template>
  <div class="region-fields">
    <v-autocomplete
      :model-value="country"
      :items="store.countries"
      item-title="name"
      item-value="code"
      label="Country"
      clearable
      v-bind="field"
      @update:model-value="setCountry"
    />
    <v-autocomplete
      :model-value="subdivision"
      :items="subdivisions"
      item-title="name"
      item-value="code"
      label="Region"
      clearable
      :disabled="!subdivisions.length"
      :hint="country && !subdivisions.length ? 'This country has no regional holidays.' : ''"
      persistent-hint
      v-bind="field"
      @update:model-value="emit('update:subdivision', $event ?? null)"
    />
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted } from 'vue'
import { useLeavePoliciesStore } from '@/stores/leavePolicies'

const props = defineProps<{ country: string | null; subdivision: string | null }>()
const emit = defineEmits<{
  'update:country': [value: string | null]
  'update:subdivision': [value: string | null]
}>()

const store = useLeavePoliciesStore()
const field = { variant: 'outlined', density: 'compact', hideDetails: 'auto' } as const

const subdivisions = computed(
  () => store.countries.find(c => c.code === props.country)?.subdivisions ?? [],
)

function setCountry(value: string | null): void {
  emit('update:country', value ?? null)
  emit('update:subdivision', null)
}

onMounted(() => {
  void store.fetchCountries()
})
</script>

<style scoped>
.region-fields {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 12px;
}
@media (max-width: 600px) {
  .region-fields {
    grid-template-columns: minmax(0, 1fr);
  }
}
</style>
