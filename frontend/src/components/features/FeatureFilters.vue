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

<!-- Search, repository, which features to show, and the last-touched sort. -->
<template>
  <div class="feature-filters" role="search">
    <v-text-field
      v-model="query"
      label="Search features"
      prepend-inner-icon="mdi-magnify"
      variant="outlined"
      density="compact"
      hide-details
      clearable
      class="feature-filters__search"
      @click:clear="query = ''"
    />
    <v-select
      v-model="repoId"
      :items="repoOptions"
      label="Repository"
      variant="outlined"
      density="compact"
      hide-details
      :disabled="repos.length === 0"
      class="feature-filters__select"
    />
    <v-select v-model="mode" :items="MODE_OPTIONS" label="Show" variant="outlined" density="compact" hide-details class="feature-filters__select" />
    <v-select
      v-model="touchedSort"
      :items="SORT_OPTIONS"
      label="Sort"
      variant="outlined"
      density="compact"
      hide-details
      class="feature-filters__select"
    />
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import type { FeatureViewMode } from '@/stores/features'
import type { RepoInfo } from '@/types'

const props = defineProps<{ repos: RepoInfo[] }>()

const query = defineModel<string>('query', { required: true })
const repoId = defineModel<string>('repoId', { required: true })
const mode = defineModel<FeatureViewMode>('mode', { required: true })
const touchedSort = defineModel<'asc' | 'desc'>('touchedSort', { required: true })

// One filter at a time, not a cumulative widening; the backend takes the
// same values as ``mode``.
const MODE_OPTIONS: Array<{ title: string; value: FeatureViewMode }> = [
  { title: 'Live', value: 'active' },
  { title: 'Live and in progress', value: 'all' },
  { title: 'In progress', value: 'in_progress' },
  { title: 'Deactivated', value: 'deactivated' },
]
const SORT_OPTIONS = [
  { title: 'Recently touched', value: 'desc' },
  { title: 'Least recently touched', value: 'asc' },
]

const repoOptions = computed(() => [
  { title: 'All repositories', value: '' },
  ...props.repos.map(r => ({ title: r.name, value: r.id })),
])
</script>

<style scoped>
.feature-filters {
  display: flex;
  flex-wrap: wrap;
  gap: 10px;
}
.feature-filters__search {
  flex: 1 1 240px;
  max-width: 320px;
}
.feature-filters__select {
  flex: 0 1 210px;
  min-width: 170px;
}
@media (max-width: 600px) {
  .feature-filters__search,
  .feature-filters__select {
    flex-basis: 100%;
    max-width: none;
  }
}
</style>
