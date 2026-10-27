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

<!-- Teams tab on the Members page: group members and map them to the
     repositories they own, so BUDs route to the right squad. -->
<template>
  <div class="teams-tab">
    <div class="teams-tab__bar">
      <v-select
        v-model="statusFilter"
        :items="STATUS_OPTIONS"
        label="Show"
        density="compact"
        hide-details
        variant="outlined"
        class="teams-tab__filter"
        @update:model-value="(v: TeamFilter) => store.fetchTeams(v === 'all')"
      />
      <v-btn color="primary" variant="flat" prepend-icon="mdi-plus" @click="openCreate">New team</v-btn>
    </div>

    <AppCallout v-if="store.error" variant="error">
      {{ store.error }}
      <template #actions>
        <v-btn icon="mdi-close" variant="text" size="small" aria-label="Dismiss" @click="store.error = null" />
      </template>
    </AppCallout>

    <div v-if="store.loading" class="d-flex justify-center py-12">
      <v-progress-circular indeterminate color="primary" aria-label="Loading teams" />
    </div>
    <AppCallout v-else-if="store.teams.length === 0" variant="info" title="No teams yet" icon="mdi-account-group-outline">
      Group members and map them to the repositories they own. Auto-assignment then routes BUDs to the
      right team based on the repositories a BUD touches.
    </AppCallout>
    <TeamsTable v-else :teams="visibleTeams" @edit="openEdit" @archive="toggleArchive" />

    <v-dialog v-model="createOpen" max-width="480">
      <v-card>
        <v-card-title>New team</v-card-title>
        <v-card-text>
          <v-text-field v-model="newName" label="Name" variant="outlined" density="compact" autofocus />
          <v-textarea v-model="newDescription" label="Description (optional)" variant="outlined" density="compact" rows="2" />
        </v-card-text>
        <v-card-actions class="px-4 pb-4">
          <v-spacer />
          <v-btn variant="text" @click="createOpen = false">Cancel</v-btn>
          <v-btn color="primary" variant="flat" :disabled="!newName.trim()" @click="onCreate">Create</v-btn>
        </v-card-actions>
      </v-card>
    </v-dialog>

    <TeamEditDialog v-model="editOpen" :team-id="editingId" />
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import AppCallout from '@/components/common/AppCallout.vue'
import TeamEditDialog from './TeamEditDialog.vue'
import TeamsTable from './TeamsTable.vue'
import { useMembersStore } from '@/stores/members'
import { useSettingsStore } from '@/stores/settings'
import { useTeamsStore } from '@/stores/teams'

type TeamFilter = 'active' | 'all'
const STATUS_OPTIONS: { title: string; value: TeamFilter }[] = [
  { title: 'Active', value: 'active' },
  { title: 'Active and archived', value: 'all' },
]

const store = useTeamsStore()
const membersStore = useMembersStore()
const settingsStore = useSettingsStore()

const statusFilter = ref<TeamFilter>('active')
const editingId = ref<string | null>(null)
const editOpen = ref(false)
const createOpen = ref(false)
const newName = ref('')
const newDescription = ref('')

const visibleTeams = computed(() =>
  statusFilter.value === 'active' ? store.teams.filter(t => t.status === 'active') : store.teams,
)

// The table previews members and repositories from each team's detail,
// so every visible team's detail is fetched once and cached.
async function loadPreviewDetails(): Promise<void> {
  await Promise.all(visibleTeams.value.filter(t => !store.detailsById[t.id]).map(t => store.fetchTeam(t.id)))
}

watch(visibleTeams, () => {
  void loadPreviewDetails()
})

function openCreate(): void {
  newName.value = ''
  newDescription.value = ''
  createOpen.value = true
}

async function onCreate(): Promise<void> {
  const created = await store.createTeam({ name: newName.value.trim(), description: newDescription.value.trim() || null })
  if (!created) return
  createOpen.value = false
  await openEdit(created.id)
}

async function openEdit(id: string): Promise<void> {
  editingId.value = id
  editOpen.value = true
  if (!store.detailsById[id]) await store.fetchTeam(id)
}

async function toggleArchive(id: string): Promise<void> {
  const team = store.teams.find(t => t.id === id)
  if (!team) return
  if (team.status === 'active') await store.archiveTeam(id)
  else await store.updateTeam(id, { status: 'active' })
}

onMounted(async () => {
  await Promise.all([
    store.fetchTeams(false),
    membersStore.members.length === 0 ? membersStore.fetchMembers() : Promise.resolve(),
    settingsStore.repos.length === 0 ? settingsStore.fetchRepos() : Promise.resolve(),
  ])
  await loadPreviewDetails()
})
</script>

<style scoped>
.teams-tab {
  display: flex;
  flex-direction: column;
  gap: 16px;
}
.teams-tab__bar {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
}
.teams-tab__filter {
  max-width: 220px;
}
</style>
