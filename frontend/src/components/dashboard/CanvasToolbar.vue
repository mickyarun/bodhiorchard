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

<!-- Controls over the Graph and Garden canvases: a code-map summary, the
     repository picker, cross-repo links (garden) and back (graph). -->
<template>
  <div class="canvas-toolbar">
    <v-btn
      v-if="mode === 'graph' && graphHasSelection"
      variant="text"
      prepend-icon="mdi-arrow-left"
      @click="emit('graph-back')"
    >
      All features
    </v-btn>
    <span v-if="data" class="canvas-toolbar__summary">{{ summary }}</span>
    <v-spacer />
    <v-select
      v-if="repoNames.length > 1"
      v-model="visibleRepos"
      :items="repoNames"
      label="Repositories"
      density="compact"
      multiple
      hide-details
      class="canvas-toolbar__repos"
    >
      <template #prepend-item>
        <v-list-item title="All repositories" @click="emit('toggle-all-repos')">
          <template #prepend>
            <v-checkbox-btn
              :model-value="visibleRepos.length === repoNames.length"
              :indeterminate="visibleRepos.length > 0 && visibleRepos.length < repoNames.length"
            />
          </template>
        </v-list-item>
        <v-divider />
      </template>
      <template #selection="{ index }">
        <span v-if="index === 0">
          {{ visibleRepos.length === repoNames.length ? 'All' : `${visibleRepos.length} of ${repoNames.length}` }}
        </span>
      </template>
    </v-select>
    <v-btn
      v-if="mode === 'garden' && data?.relationships?.length"
      variant="outlined"
      :aria-pressed="relationsOn"
      prepend-icon="mdi-vector-polyline"
      @click="emit('toggle-relations')"
    >
      Cross-repo links
    </v-btn>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import type { DashboardViewMode } from '@/composables/useDashboardViewMode'
import type { TreeData } from '@/types/dashboard'

const props = defineProps<{
  mode: DashboardViewMode
  data: TreeData | null
  repoNames: string[]
  relationsOn: boolean
  graphHasSelection: boolean
}>()

const visibleRepos = defineModel<string[]>('visibleRepos', { required: true })
const emit = defineEmits<{
  'toggle-all-repos': []
  'toggle-relations': []
  'graph-back': []
}>()

const summary = computed(() => {
  const d = props.data
  if (!d) return ''
  const parts = [`${d.total_features} features`, `${d.members.length} members`]
  if (d.threats.length) parts.push(`${d.threats.length} security findings`)
  return parts.join(' · ')
})
</script>

<style scoped>
.canvas-toolbar {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 8px 12px;
}
.canvas-toolbar__summary {
  font-size: var(--text-sm);
  color: rgb(var(--v-theme-on-surface-variant));
}
.canvas-toolbar__repos {
  flex: 0 1 240px;
  min-width: 160px;
}
</style>
