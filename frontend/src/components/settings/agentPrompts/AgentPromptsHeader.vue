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

<!-- Sticky header of the Agent Prompts page: title, actions, search, the
     filter chips and the store's error / saved callouts. -->
<template>
  <header class="page-header pa-6 pb-5">
    <div class="d-flex align-start justify-space-between flex-wrap ga-4">
      <div>
        <div class="d-flex align-center ga-2 mb-1">
          <v-icon icon="mdi-robot-happy-outline" size="22" color="primary" />
          <h1 class="page-title">Agent Prompts</h1>
        </div>
        <div class="page-subtitle">
          Tune the persona, tooling, and prompt that drives each AI agent
          skill. Add your own and pick a default per agent type.
        </div>
      </div>
      <div class="d-flex ga-2 align-center">
        <v-btn
          color="primary"
          variant="flat"
          prepend-icon="mdi-plus"
          class="text-none"
          @click="emit('create')"
        >
          Add custom skill
        </v-btn>
        <v-btn
          variant="text"
          prepend-icon="mdi-arrow-left"
          class="text-none text-medium-emphasis"
          :to="{ name: 'settings' }"
        >
          Back to settings
        </v-btn>
      </div>
    </div>

    <!-- Search + filter -->
    <div class="d-flex align-center ga-3 mt-5 flex-wrap">
      <v-text-field
        v-model="search"
        placeholder="Search skills, descriptions, slugs…"
        prepend-inner-icon="mdi-magnify"
        variant="solo-filled"
        density="compact"
        hide-details
        flat
        single-line
        class="search-input"
        clearable
      />
      <v-chip-group
        v-model="filterMode"
        mandatory
        selected-class="filter-chip-selected"
        class="filter-chips"
      >
        <v-chip value="all" variant="tonal" size="small" filter>All</v-chip>
        <v-chip value="custom" variant="tonal" size="small" filter>Custom</v-chip>
        <v-chip value="modified" variant="tonal" size="small" filter>Modified</v-chip>
      </v-chip-group>
    </div>

    <AppCallout v-if="store.error" variant="error" class="mt-4">
      {{ store.error }}
      <template #actions>
        <v-btn icon="mdi-close" variant="text" size="small" aria-label="Dismiss" @click="store.error = null" />
      </template>
    </AppCallout>
    <AppCallout v-if="store.saveSuccess" variant="success" class="mt-4">
      Saved.
      <template #actions>
        <v-btn icon="mdi-close" variant="text" size="small" aria-label="Dismiss" @click="store.saveSuccess = false" />
      </template>
    </AppCallout>
  </header>
</template>

<script setup lang="ts">
import AppCallout from '@/components/common/AppCallout.vue'
import { useAgentSkillsStore } from '@/stores/agentSkills'
import type { SkillFilterMode } from './agentPrompts.util'

const search = defineModel<string>('search', { required: true })
const filterMode = defineModel<SkillFilterMode>('filterMode', { required: true })
const emit = defineEmits<{ create: [] }>()

const store = useAgentSkillsStore()
</script>

<style scoped>
.page-header {
  flex-shrink: 0;
  position: sticky;
  top: 0;
  z-index: 2;
  background: rgb(var(--v-theme-background));
  border-bottom: 1px solid rgba(var(--v-theme-on-surface), 0.06);
  backdrop-filter: blur(8px);
}

.page-title {
  font-size: 22px;
  font-weight: 600;
  letter-spacing: -0.01em;
  margin: 0;
  color: rgb(var(--v-theme-on-surface));
}

.page-subtitle {
  font-size: 13px;
  color: rgba(var(--v-theme-on-surface), 0.6);
  max-width: 560px;
  line-height: 1.5;
}

.search-input {
  max-width: 420px;
  flex: 1;
}

.search-input :deep(.v-field) {
  background: rgba(var(--v-theme-on-surface), 0.04);
  border-radius: 10px;
}

.filter-chips :deep(.v-chip) {
  text-transform: none;
  font-weight: 500;
}

.filter-chip-selected {
  background-color: rgba(var(--v-theme-primary), 0.18) !important;
  color: rgb(var(--v-theme-primary)) !important;
}
</style>
