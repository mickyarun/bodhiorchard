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

<!-- Bugs: the environment toggle and Report a bug in the header, severity
     and status filters (plus the BUD filter when linked from the board), the
     bug table, and the open bug in a side sheet. -->
<template>
  <AppPage title="Bugs" :subtitle="subtitle">
    <template #actions>
      <AppPillToggle v-model="scope" :options="BUG_SCOPE_OPTIONS" aria-label="Environment" />
      <v-btn v-if="canReportBugs" color="primary" variant="flat" prepend-icon="mdi-plus" @click="showCreate = true">
        Report a bug
      </v-btn>
    </template>

    <div class="bugs-page__filters">
      <BoardFilterMenu v-model="severity" label="Severity" all-label="All severities" :options="BUG_SEVERITY_OPTIONS" />
      <BoardFilterMenu v-model="status" label="Status" all-label="All statuses" :options="BUG_STATUS_GROUP_OPTIONS" />
      <span v-if="budId" class="bugs-page__bud">
        Bugs for {{ budLabel }}
        <v-btn variant="text" size="small" prepend-icon="mdi-close" @click="clearBud">Show all bugs</v-btn>
      </span>
    </div>

    <div v-if="loading && !loaded.length" class="bugs-page__loading">
      <v-progress-circular indeterminate color="primary" aria-label="Loading bugs" />
    </div>
    <p v-else-if="!rows.length" class="bugs-page__empty">{{ emptyText }}</p>
    <BugTable v-else :bugs="rows" :now="now" :show-type="scope === 'all'" :label="budId ? `Bugs for ${budLabel}` : 'Bugs'" @open="openBug" />

    <AppSideSheet v-model="showDetail" :title="detailTitle" :width="600">
      <BugDetailPanel />
    </AppSideSheet>

    <BugCreateDialog
      v-model="showCreate"
      :bud-id="budId ?? undefined"
      :default-bug-type="scope === 'testing' ? 'testing' : 'production'"
      @created="load"
    />

    <v-snackbar v-model="errorOpen" color="error" location="bottom right" :timeout="4000">
      {{ bugsStore.error }}
    </v-snackbar>
  </AppPage>
</template>

<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import AppPage from '@/components/common/AppPage.vue'
import AppPillToggle from '@/components/common/AppPillToggle.vue'
import AppSideSheet from '@/components/common/AppSideSheet.vue'
import BoardFilterMenu from '@/components/buds/board/BoardFilterMenu.vue'
import BugDetailPanel from '@/components/bugs/BugDetailPanel.vue'
import BugTable from '@/components/bugs/BugTable.vue'
import { useBugList } from '@/composables/useBugList'
import { useNow } from '@/composables/useNow'
import { usePermissions } from '@/composables/usePermissions'
import type { BugListItem } from '@/types'
import { BUG_SCOPE_OPTIONS, BUG_SEVERITY_OPTIONS, BUG_STATUS_GROUP_OPTIONS, bugRef } from '@/utils/bugList'
import BugCreateDialog from './BugCreateDialog.vue'

const { bugsStore, scope, severity, status, budId, budLabel, loading, loaded, rows, open, filtering, load, clearBud } =
  useBugList()
const { canReportBugs } = usePermissions()
const now = useNow()

const showCreate = ref(false)
const showDetail = ref(false)

const subtitle = computed(() => {
  const count = open.value === 1 ? '1 open' : `${open.value} open`
  return `${count} · new bugs are linked to the BUD that caused them automatically`
})

const emptyText = computed(() => {
  if (loaded.value.length && filtering.value) return 'No bugs match these filters.'
  const kind = scope.value === 'all' ? 'bugs' : `${scope.value} bugs`
  return budId.value ? `No ${kind} for ${budLabel.value}.` : `No ${kind} reported yet.`
})

const detailTitle = computed(() => (bugsStore.currentBug ? bugRef(bugsStore.currentBug.bugNumber) : 'Bug'))

async function openBug(bug: BugListItem): Promise<void> {
  await bugsStore.fetchBug(bug.id)
  if (bugsStore.currentBug?.id === bug.id) showDetail.value = true
}

// Errors from loading or saving show in a snackbar; closing it clears the
// error so the same message can show again next time.
const errorOpen = computed({
  get: () => !!bugsStore.error,
  set: open => {
    if (!open) bugsStore.error = null
  },
})

// The open bug belongs to the list it was opened from.
watch(budId, () => (showDetail.value = false))
</script>

<style scoped>
.bugs-page__filters {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 8px;
}
.bugs-page__bud {
  display: inline-flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 4px 8px;
  margin-left: auto;
  font-size: 14px;
  font-weight: 500;
}
.bugs-page__loading {
  display: flex;
  justify-content: center;
  padding: 48px 0;
}
.bugs-page__empty {
  margin: 0;
  padding: 48px 16px;
  text-align: center;
  font-size: 14px;
  color: rgb(var(--v-theme-on-surface-variant));
  background: rgb(var(--v-theme-surface));
  border: 1px solid rgb(var(--v-theme-rule));
  border-radius: 12px;
}
@media (max-width: 600px) {
  .bugs-page__bud {
    margin-left: 0;
  }
}
</style>
