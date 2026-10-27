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

<!-- Board header: title and count, the search and dropdown filters, the
     priority sort and Discarded toggles, and the one primary action. -->
<template>
  <header class="board-header">
    <div class="board-header__title">
      <h1>Board</h1>
      <span class="board-header__count">{{ countLabel }}</span>
    </div>
    <v-text-field
      v-model="query"
      label="Filter by title or BUD-###"
      prepend-inner-icon="mdi-magnify"
      variant="outlined"
      density="compact"
      hide-details
      clearable
      class="board-header__search"
    />
    <div class="board-header__filters">
      <BoardFilterMenu v-model="assignee" label="Assignee" all-label="All assignees" :options="assigneeOptions" />
      <BoardFilterMenu v-model="priority" label="Priority" all-label="All priorities" :options="priorityOptions" />
      <BoardFilterMenu
        v-model="team"
        label="Team"
        all-label="All teams"
        :options="teamOptions"
        :disabled="teamOptions.length === 0"
        disabled-hint="No teams yet. Add them in Settings, Teams."
      />
    </div>
    <div class="board-header__tools">
      <v-btn
        variant="text"
        size="small"
        :icon="sortByPriority ? 'mdi-sort-descending' : 'mdi-sort-variant'"
        :aria-pressed="sortByPriority"
        :color="sortByPriority ? 'primary' : undefined"
        aria-label="Sort cards by priority, P0 first"
        title="Sort cards by priority (P0 first) within each column"
        @click="sortByPriority = !sortByPriority"
      />
      <v-btn
        variant="text"
        :aria-pressed="showDiscarded"
        :color="showDiscarded ? 'primary' : undefined"
        @click="showDiscarded = !showDiscarded"
      >
        Discarded
      </v-btn>
      <v-btn
        v-if="canConfigure"
        icon="mdi-cog-outline"
        variant="text"
        size="small"
        aria-label="Customize QA framework and lifecycle stages"
        title="Customize QA framework and lifecycle stages"
        :to="{ name: 'settings-qa-automation' }"
      />
      <v-btn v-if="canCreate" color="primary" variant="flat" prepend-icon="mdi-plus" @click="emit('new-bud')">
        New BUD
      </v-btn>
    </div>
  </header>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import BoardFilterMenu from './BoardFilterMenu.vue'
import type { BUDPriority } from '@/types'
import type { FilterOption } from '@/utils/budBoard'

const props = defineProps<{
  shown: number
  total: number
  filtering: boolean
  assigneeOptions: FilterOption[]
  priorityOptions: FilterOption<BUDPriority>[]
  teamOptions: FilterOption[]
  canCreate: boolean
  canConfigure: boolean
}>()

const emit = defineEmits<{ 'new-bud': [] }>()

const query = defineModel<string>('query', { required: true })
const assignee = defineModel<string | null>('assignee', { required: true })
const priority = defineModel<BUDPriority | null>('priority', { required: true })
const team = defineModel<string | null>('team', { required: true })
const sortByPriority = defineModel<boolean>('sortByPriority', { required: true })
const showDiscarded = defineModel<boolean>('showDiscarded', { required: true })

const countLabel = computed(() => {
  const total = props.total === 1 ? '1 BUD' : `${props.total} BUDs`
  return props.filtering ? `${props.shown} of ${total}` : total
})
</script>

<style scoped>
.board-header {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 12px;
}
.board-header__title {
  display: flex;
  align-items: baseline;
  gap: 10px;
  margin-right: 8px;
}
.board-header__title h1 {
  margin: 0;
  font-size: 28px;
  line-height: 34px;
  font-weight: 600;
  letter-spacing: var(--tracking-display);
}
.board-header__count {
  font-size: 14px;
  color: rgb(var(--v-theme-on-surface-variant));
  white-space: nowrap;
}
.board-header__search {
  flex: 0 1 260px;
  min-width: 200px;
}
.board-header__filters,
.board-header__tools {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 8px;
}
.board-header__tools {
  margin-left: auto;
}
@media (max-width: 600px) {
  .board-header__title h1 {
    font-size: 24px;
    line-height: 30px;
  }
  .board-header__search {
    flex-basis: 100%;
  }
  .board-header__tools {
    margin-left: 0;
  }
}
</style>
