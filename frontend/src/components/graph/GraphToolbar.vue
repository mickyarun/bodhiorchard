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
  <div class="graph-toolbar" @wheel.stop @pointerdown.stop @mousedown.stop @click.stop>
    <v-card variant="tonal" class="pa-2 d-flex align-center ga-2 flex-wrap" density="compact">
      <!-- Cross-repo links toggle -->
      <v-btn
        :variant="crossRepo ? 'flat' : 'text'"
        :color="crossRepo ? 'cyan' : undefined"
        size="small"
        prepend-icon="mdi-link-variant"
        @click="toggleCrossRepo"
      >
        Cross-repo
      </v-btn>

      <!-- Bus factor toggle -->
      <v-btn
        :variant="busFactor ? 'flat' : 'text'"
        :color="busFactor ? 'warning' : undefined"
        size="small"
        prepend-icon="mdi-account-alert"
        @click="toggleBusFactor"
      >
        Bus Factor
      </v-btn>

      <!-- Status colors toggle -->
      <v-btn
        :variant="statusColors ? 'flat' : 'text'"
        :color="statusColors ? 'info' : undefined"
        size="small"
        prepend-icon="mdi-palette"
        @click="toggleStatus"
      >
        Status
      </v-btn>

      <!-- Threats toggle -->
      <v-btn
        :variant="threats ? 'flat' : 'text'"
        :color="threats ? 'error' : undefined"
        size="small"
        prepend-icon="mdi-bug"
        @click="toggleThreats"
      >
        Threats
      </v-btn>

      <!-- BUD badges toggle -->
      <v-btn
        :variant="budBadges ? 'flat' : 'text'"
        :color="budBadges ? 'success' : undefined"
        size="small"
        prepend-icon="mdi-seed-outline"
        @click="toggleBudBadges"
      >
        BUD Stage
      </v-btn>

      <v-divider vertical class="mx-1" />

      <!-- Repo filter -->
      <v-autocomplete
        v-model="selectedRepo"
        :items="repoItems"
        placeholder="Filter by repo"
        density="compact"
        variant="outlined"
        hide-details
        clearable
        autocomplete="off"
        class="repo-filter"
        :menu-props="{ maxHeight: 250, class: 'graph-dropdown' }"
        @update:model-value="onRepoFilter"
      />

      <!-- Developer filter -->
      <v-autocomplete
        v-model="selectedDev"
        :items="devItems"
        item-title="name"
        item-value="userId"
        placeholder="Filter by developer"
        density="compact"
        variant="outlined"
        hide-details
        clearable
        autocomplete="off"
        class="dev-filter"
        :menu-props="{ maxHeight: 250, class: 'graph-dropdown' }"
        @update:model-value="onDevFilter"
      />
    </v-card>

    <!-- Active status legend -->
    <div v-if="statusColors" class="status-legend mt-2 d-flex ga-2">
      <v-chip size="x-small" color="blue" label>planned</v-chip>
      <v-chip size="x-small" color="orange" label>in progress</v-chip>
      <v-chip size="x-small" color="green" label>implemented</v-chip>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed } from 'vue'

interface MemberItem {
  userId: string
  name: string
}

const props = defineProps<{
  members: MemberItem[]
  repos: string[]
}>()

const emit = defineEmits<{
  (e: 'toggle-cross-repo', active: boolean): void
  (e: 'toggle-bus-factor', active: boolean): void
  (e: 'toggle-status', active: boolean): void
  (e: 'toggle-threats', active: boolean): void
  (e: 'toggle-bud-badges', active: boolean): void
  (e: 'filter-developer', userId: string | null): void
  (e: 'filter-repo', repoName: string | null): void
}>()

const crossRepo = ref(true)
const busFactor = ref(false)
const statusColors = ref(false)
const threats = ref(false)
const budBadges = ref(false)
const selectedDev = ref<string | null>(null)
const selectedRepo = ref<string | null>(null)

const devItems = computed(() => props.members)
const repoItems = computed(() => props.repos)

function toggleCrossRepo(): void {
  crossRepo.value = !crossRepo.value
  emit('toggle-cross-repo', crossRepo.value)
}

function toggleBusFactor(): void {
  busFactor.value = !busFactor.value
  emit('toggle-bus-factor', busFactor.value)
}

function toggleStatus(): void {
  statusColors.value = !statusColors.value
  emit('toggle-status', statusColors.value)
}

function toggleThreats(): void {
  threats.value = !threats.value
  emit('toggle-threats', threats.value)
}

function toggleBudBadges(): void {
  budBadges.value = !budBadges.value
  emit('toggle-bud-badges', budBadges.value)
}

function onRepoFilter(repoName: string | null): void {
  emit('filter-repo', repoName)
}

function onDevFilter(userId: string | null): void {
  emit('filter-developer', userId)
}
</script>

<style scoped>
.graph-toolbar {
  position: absolute;
  bottom: 16px;
  left: 16px;
  z-index: 10;
  max-width: calc(100% - 32px);
}

.repo-filter {
  max-width: 200px;
  min-width: 150px;
}

.dev-filter {
  max-width: 220px;
  min-width: 180px;
}

.status-legend {
  padding-left: 4px;
}
</style>

<!-- Unscoped: stop wheel events on the teleported dropdown overlay -->
<style>
.graph-dropdown .v-list {
  overscroll-behavior: contain;
}
</style>
