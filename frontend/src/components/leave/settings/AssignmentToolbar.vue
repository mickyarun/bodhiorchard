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

<!-- Search and policy filter above the people table. Typing waits a moment
     before searching, so each keystroke isn't a request. -->
<template>
  <div class="toolbar">
    <v-text-field
      v-model="typed"
      label="Search people"
      placeholder="Name or email"
      prepend-inner-icon="mdi-magnify"
      clearable
      class="toolbar__search"
      v-bind="FIELD_PROPS"
    />
    <v-select
      v-if="filterItems"
      v-model="filter"
      :items="filterItems"
      label="Leave policy"
      class="toolbar__filter"
      v-bind="FIELD_PROPS"
    />
  </div>
</template>

<script setup lang="ts">
import { ref, watch } from 'vue'
import { useDebounced } from '@/composables/useDebounced'
import { FIELD_PROPS } from '@/utils/leavePolicyDisplay'

defineProps<{ filterItems?: { title: string; value: string }[] }>()
const search = defineModel<string>('search', { required: true })
const filter = defineModel<string>('filter', { required: true })

// Clearing the field sets null; the search is always a string.
const typed = ref<string | null>(search.value)
const settled = useDebounced(typed)
watch(settled, value => {
  search.value = value ?? ''
})
</script>

<style scoped>
.toolbar {
  display: flex;
  flex-wrap: wrap;
  gap: 12px 16px;
  margin-bottom: 16px;
}
.toolbar__search {
  flex: 0 1 320px;
  min-width: 220px;
}
.toolbar__filter {
  flex: 0 1 260px;
  min-width: 200px;
}
</style>
