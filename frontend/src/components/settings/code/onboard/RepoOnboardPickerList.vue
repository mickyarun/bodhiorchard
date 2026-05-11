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
  Owner-grouped checkbox list for the bulk-import picker.

  Note on virtualisation: ``v-virtual-scroll`` does not compose cleanly
  with grouped headers (it virtualises a flat array, not nested
  sections). For the ≤200-row cap the bulk-onboard endpoint enforces,
  plain ``v-list`` rendering is comfortable and keeps the row layout
  simple. If repo counts grow, switch to a flattened {kind: 'header' |
  'row'} array fed into v-virtual-scroll with a fixed item-height.
-->
<template>
  <v-card variant="outlined" class="pa-0">
    <v-text-field
      v-model="query"
      :placeholder="SEARCH_PLACEHOLDER"
      prepend-inner-icon="mdi-magnify"
      density="comfortable"
      variant="solo-filled"
      flat
      hide-details
      clearable
      class="ma-3"
    />
    <v-divider />
    <div v-if="filteredRepos.length === 0" class="pa-6 text-center text-medium-emphasis">
      {{ EMPTY_MESSAGE }}
    </div>
    <template v-else>
      <div class="px-4 pt-2 text-caption text-medium-emphasis">
        {{ rangeCaption }}
      </div>
      <v-list density="compact" lines="two" class="py-0">
        <template v-for="group in pagedOwners" :key="group.owner">
          <div class="d-flex align-center ga-2 px-3 py-2 bg-surface-variant">
            <v-avatar size="24"><v-img :src="group.avatarUrl" /></v-avatar>
            <span class="font-weight-medium text-body-1">{{ group.owner }}</span>
            <v-spacer />
            <div class="select-all-toggle d-flex align-center">
              <v-checkbox-btn
                :model-value="ownerCheckState(group)"
                :indeterminate="ownerIsPartial(group)"
                density="compact"
                hide-details
                class="ma-0 pa-0"
                @update:model-value="onOwnerToggle(group, $event as boolean)"
              />
              <span
                class="text-caption select-all-label"
                @click="onOwnerToggle(group, !ownerCheckState(group))"
              >{{ SELECT_ALL_LABEL }}</span>
            </div>
          </div>
          <v-list-item
            v-for="repo in group.repos"
            :key="repo.fullName"
            :disabled="repo.alreadyTracked"
            @click="onRowClick(repo)"
          >
            <template #prepend>
              <v-checkbox-btn
                :model-value="selection.has(repo.fullName)"
                :disabled="repo.alreadyTracked"
                density="compact"
                hide-details
                @click.stop
                @update:model-value="emit('toggle:repo', repo.fullName)"
              />
            </template>
            <v-list-item-title class="d-flex align-center ga-2">
              <span class="text-body-2">{{ repo.fullName }}</span>
              <v-chip v-if="repo.private" size="x-small" variant="tonal" color="warning">
                {{ PRIVATE_LABEL }}
              </v-chip>
              <v-chip v-if="repo.alreadyTracked" size="x-small" variant="tonal" color="success">
                {{ ALREADY_TRACKED_LABEL }}
              </v-chip>
            </v-list-item-title>
            <v-list-item-subtitle>
              {{ DEFAULT_BRANCH_PREFIX }}{{ repo.defaultBranch }}
            </v-list-item-subtitle>
          </v-list-item>
        </template>
      </v-list>
      <div v-if="totalPages > 1" class="d-flex justify-center py-2">
        <v-pagination
          v-model="currentPage"
          :length="totalPages"
          density="comfortable"
          total-visible="5"
        />
      </div>
    </template>
  </v-card>
</template>

<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import type { InstallableRepo } from '@/types/repoOnboard'

const SEARCH_PLACEHOLDER = 'Search repositories…'
const EMPTY_MESSAGE = 'No repositories match your search.'
const PRIVATE_LABEL = 'private'
const ALREADY_TRACKED_LABEL = 'already tracked'
const DEFAULT_BRANCH_PREFIX = 'default branch: '
const SELECT_ALL_LABEL = 'Select all'
const REPOS_PER_PAGE = 25

interface OwnerGroup {
  owner: string
  avatarUrl: string
  repos: InstallableRepo[]
}

const props = defineProps<{
  repos: InstallableRepo[]
  selection: Set<string>
}>()

const emit = defineEmits<{
  'toggle:repo': [fullName: string]
  'toggle:owner': [ownerLogin: string, allSelected: boolean]
}>()

const query = ref<string>('')
const currentPage = ref<number>(1)

const filteredRepos = computed<InstallableRepo[]>(() => {
  const q = query.value.trim().toLowerCase()
  // Primary sort: pushedAt desc; nulls go last and sort alphabetically
  // among themselves so the order is stable across renders.
  const sorted = [...props.repos].sort((a, b) => {
    const ap = pushedAtMs(a.pushedAt)
    const bp = pushedAtMs(b.pushedAt)
    if (ap !== bp) return bp - ap
    return a.fullName.localeCompare(b.fullName)
  })
  if (!q) return sorted
  return sorted.filter((r) => r.fullName.toLowerCase().includes(q))
})

function pushedAtMs(value: string | null): number {
  // ``Number.NEGATIVE_INFINITY`` parks null/invalid timestamps after every
  // real one when sorting descending.
  if (!value) return Number.NEGATIVE_INFINITY
  const ms = Date.parse(value)
  return Number.isNaN(ms) ? Number.NEGATIVE_INFINITY : ms
}

const totalPages = computed<number>(() =>
  Math.max(1, Math.ceil(filteredRepos.value.length / REPOS_PER_PAGE)),
)

const pagedRepos = computed<InstallableRepo[]>(() => {
  const start = (currentPage.value - 1) * REPOS_PER_PAGE
  return filteredRepos.value.slice(start, start + REPOS_PER_PAGE)
})

const pagedOwners = computed<OwnerGroup[]>(() => {
  const groups = new Map<string, OwnerGroup>()
  for (const repo of pagedRepos.value) {
    let group = groups.get(repo.ownerLogin)
    if (!group) {
      group = { owner: repo.ownerLogin, avatarUrl: repo.ownerAvatarUrl, repos: [] }
      groups.set(repo.ownerLogin, group)
    }
    group.repos.push(repo)
  }
  return [...groups.values()]
})

const rangeCaption = computed<string>(() => {
  const total = filteredRepos.value.length
  if (total === 0) return ''
  const start = (currentPage.value - 1) * REPOS_PER_PAGE + 1
  const end = Math.min(total, currentPage.value * REPOS_PER_PAGE)
  return `Showing ${start}–${end} of ${total}`
})

watch(query, () => {
  currentPage.value = 1
})

watch(totalPages, (next) => {
  if (currentPage.value > next) currentPage.value = next
})

function selectableInGroup(group: OwnerGroup): InstallableRepo[] {
  return group.repos.filter((r) => !r.alreadyTracked)
}

function ownerCheckState(group: OwnerGroup): boolean {
  const selectable = selectableInGroup(group)
  if (selectable.length === 0) return false
  return selectable.every((r) => props.selection.has(r.fullName))
}

function ownerIsPartial(group: OwnerGroup): boolean {
  const selectable = selectableInGroup(group)
  const checked = selectable.filter((r) => props.selection.has(r.fullName)).length
  return checked > 0 && checked < selectable.length
}

function onOwnerToggle(group: OwnerGroup, next: boolean): void {
  emit('toggle:owner', group.owner, next)
}

function onRowClick(repo: InstallableRepo): void {
  if (repo.alreadyTracked) return
  emit('toggle:repo', repo.fullName)
}
</script>

<style scoped>
.select-all-toggle :deep(.v-selection-control) {
  min-width: auto;
}
.select-all-label {
  cursor: pointer;
  user-select: none;
  margin-left: 6px;
}
</style>
