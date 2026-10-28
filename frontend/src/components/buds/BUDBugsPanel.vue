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
  <AppPanel title="Bugs" :note="bugs.length ? `${openBugCount} open · sends back at ${threshold}` : undefined">
    <template #action>
      <v-btn variant="outlined" size="small" prepend-icon="mdi-bug-outline" @click="showCreate = true">Report bug</v-btn>
    </template>

    <!-- Testing only: how close the open bugs are to the send-back threshold. -->
    <AppCallout
      v-if="budStatus === 'testing' && openBugCount > 0"
      :variant="openBugCount >= threshold ? 'error' : 'warning'"
      class="mb-3"
    >
      <template v-if="openBugCount >= threshold">
        Bug threshold reached ({{ openBugCount }} of {{ threshold }}). The BUD went back to development.
      </template>
      <template v-else>
        {{ openBugCount }} of {{ threshold }} open bugs. {{ threshold - openBugCount }} more will send this BUD back to development.
      </template>
    </AppCallout>

    <!-- Back in development with open bugs: they block the next submit. -->
    <AppCallout v-if="budStatus === 'development' && openBugCount > 0" variant="warning" class="mb-3">
      Returned from testing. Resolve {{ openBugCount === 1 ? 'the open bug' : `all ${openBugCount} open bugs` }} before submitting again.
    </AppCallout>

    <div v-if="loading" class="d-flex justify-center py-4">
      <v-progress-circular indeterminate size="20" width="2" aria-label="Loading bugs" />
    </div>
    <p v-else-if="bugs.length === 0" class="bugs-panel__empty">No bugs linked to this BUD</p>
    <ul v-else class="bugs-panel__list">
      <li v-for="bug in bugs" :key="bug.id">
        <router-link :to="{ path: '/bugs', query: { budId } }" class="bugs-panel__row">
          <v-chip :color="BUG_SEVERITY_COLORS[bug.severity]" size="x-small" variant="tonal">{{ bug.severity }}</v-chip>
          <span class="bugs-panel__title">{{ bug.title }}</span>
          <v-chip :color="BUG_STATUS_COLORS[bug.status]" size="x-small" variant="tonal">{{ bug.status }}</v-chip>
        </router-link>
      </li>
    </ul>

    <BugCreateDialog v-model="showCreate" :bud-id="budId" @created="loadBugs" />
  </AppPanel>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useBugsStore } from '@/stores/bugs'
import { useSettingsStore } from '@/stores/settings'
import { BUG_SEVERITY_COLORS, BUG_STATUS_COLORS } from '@/types'
import type { BugListItem, BUDStatus } from '@/types'
import BugCreateDialog from '@/views/bugs/BugCreateDialog.vue'
import AppCallout from '@/components/common/AppCallout.vue'
import AppPanel from '@/components/common/AppPanel.vue'

const props = defineProps<{
  budId: string
  budStatus?: BUDStatus
}>()

const bugsStore = useBugsStore()
const settingsStore = useSettingsStore()
const bugs = ref<BugListItem[]>([])
const loading = ref(false)
const showCreate = ref(false)

const threshold = computed(
  () => settingsStore.connections.qaAutomation?.bugRejectThreshold ?? 5,
)

const openBugCount = computed(
  () => bugs.value.filter(
    (b) => b.status === 'open' || b.status === 'in-progress' || b.status === 'blocked',
  ).length,
)

async function loadBugs(): Promise<void> {
  loading.value = true
  bugs.value = await bugsStore.fetchBugsForBud(props.budId)
  loading.value = false
}

onMounted(() => loadBugs())
</script>

<style scoped>
.bugs-panel__empty {
  margin: 0;
  padding: 8px 0;
  text-align: center;
  font-size: 13px;
  color: rgb(var(--v-theme-on-surface-variant));
}
.bugs-panel__list {
  list-style: none;
  margin: 0;
  padding: 0;
  display: flex;
  flex-direction: column;
  gap: 4px;
}
.bugs-panel__row {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 8px;
  border: 1px solid rgb(var(--v-theme-rule));
  border-radius: var(--radius-input);
  color: inherit;
  text-decoration: none;
}
.bugs-panel__row:hover {
  border-color: rgba(var(--v-theme-primary), 0.55);
}
.bugs-panel__title {
  flex-grow: 1;
  min-width: 0;
  font-size: 14px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
</style>
