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
  Per-repo branch picker. One row per currently-selected repo, two
  ``v-select``s (main = required, develop = optional). Branches are
  lazy-loaded the first time a repo enters the selection — the parent
  composable owns the cache and we just emit ``request:branches`` if
  the props arrive empty.
-->
<template>
  <v-card v-if="selectedRepos.length > 0" variant="outlined" class="pa-0">
    <v-list density="comfortable" lines="two" class="py-0">
      <v-list-item v-for="repo in selectedRepos" :key="repo.fullName">
        <v-list-item-title class="text-body-2 font-weight-medium">
          {{ repo.fullName }}
        </v-list-item-title>
        <div class="d-flex ga-3 mt-2 flex-wrap">
          <v-select
            :model-value="branchesByRepo.get(repo.fullName)?.main ?? null"
            :items="branchOptions.get(repo.fullName) ?? []"
            :loading="loadingBranchesFor.has(repo.fullName)"
            :label="MAIN_LABEL"
            :placeholder="loadingBranchesFor.has(repo.fullName) ? LOADING_LABEL : SELECT_LABEL"
            density="compact"
            variant="outlined"
            hide-details
            class="branch-select"
            @update:model-value="(v) => onChange(repo.fullName, 'main', v as string | null)"
          />
          <v-select
            :model-value="branchesByRepo.get(repo.fullName)?.develop ?? null"
            :items="developItemsFor(repo.fullName)"
            :loading="loadingBranchesFor.has(repo.fullName)"
            :label="DEVELOP_LABEL"
            :placeholder="DEVELOP_PLACEHOLDER"
            density="compact"
            variant="outlined"
            hide-details
            clearable
            class="branch-select"
            @update:model-value="(v) => onChange(repo.fullName, 'develop', v as string | null)"
          />
        </div>
      </v-list-item>
    </v-list>
  </v-card>
</template>

<script setup lang="ts">
import { onMounted, watch } from 'vue'
import type { BranchPick, InstallableRepo } from '@/types/repoOnboard'

const MAIN_LABEL = 'Main / production branch'
const DEVELOP_LABEL = 'Develop branch (optional)'
const SELECT_LABEL = 'Select a branch'
const LOADING_LABEL = 'Loading…'
const DEVELOP_PLACEHOLDER = 'Optional'

type BranchKind = 'main' | 'develop'

const props = defineProps<{
  selectedRepos: InstallableRepo[]
  branchesByRepo: Map<string, BranchPick>
  branchOptions: Map<string, string[]>
  loadingBranchesFor: Set<string>
}>()

const emit = defineEmits<{
  'change:branch': [fullName: string, kind: BranchKind, branch: string | null]
  'request:branches': [fullName: string]
}>()

function ensureRequested(fullName: string): void {
  if (!props.branchOptions.has(fullName) && !props.loadingBranchesFor.has(fullName)) {
    emit('request:branches', fullName)
  }
}

function developItemsFor(fullName: string): string[] {
  const all = props.branchOptions.get(fullName) ?? []
  const main = props.branchesByRepo.get(fullName)?.main
  return main ? all.filter((b) => b !== main) : all
}

function onChange(fullName: string, kind: BranchKind, branch: string | null): void {
  emit('change:branch', fullName, kind, branch)
}

onMounted(() => {
  for (const repo of props.selectedRepos) {
    ensureRequested(repo.fullName)
  }
})

watch(
  () => props.selectedRepos.map((r) => r.fullName),
  (next) => {
    for (const fullName of next) {
      ensureRequested(fullName)
    }
  },
)
</script>

<style scoped>
.branch-select {
  min-width: 220px;
  flex: 1 1 220px;
}
</style>
