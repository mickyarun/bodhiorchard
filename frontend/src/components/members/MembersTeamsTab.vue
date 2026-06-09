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

<!-- Teams tab on the Members page. Visual contract MUST match the
     People tab: same v-table density, same surface card wrapper,
     same chip + avatar styles, same action-icon column layout. The
     row's edit dialog is the only place team membership / repo
     mapping is mutated — keeps the table itself terse. -->
<template>
  <div>
    <!-- Header + status filter + create -->
    <div class="d-flex align-center justify-space-between mb-6">
      <div>
        <div class="d-flex align-center ga-3">
          <span class="text-body-2 text-medium-emphasis">
            {{ visibleTeams.length }} team{{ visibleTeams.length !== 1 ? 's' : '' }}
          </span>
          <v-select
            v-model="statusFilter"
            :items="statusOptions"
            item-title="label"
            item-value="value"
            density="compact"
            hide-details
            variant="outlined"
            style="max-width: 180px; flex: none;"
            @update:model-value="onStatusFilterChange"
          />
        </div>
      </div>
      <v-btn color="primary" prepend-icon="mdi-account-group-outline" @click="openCreate">
        New Team
      </v-btn>
    </div>

    <v-alert v-if="store.error" type="error" variant="tonal" class="mb-4" closable>
      {{ store.error }}
    </v-alert>

    <!-- Empty state -->
    <v-card
      v-if="!store.loading && store.teams.length === 0"
      class="pa-12 text-center"
      color="surface"
    >
      <v-icon icon="mdi-account-group-outline" size="64" class="text-medium-emphasis mb-4" />
      <div class="text-h6 mb-2">No teams yet</div>
      <div class="text-body-2 text-medium-emphasis mb-6">
        Group org members and map them to the repos they own. Auto-assignment will
        route BUDs to the right squad based on which repos a BUD touches.
      </div>
      <v-btn color="primary" prepend-icon="mdi-plus" @click="openCreate">
        Create Team
      </v-btn>
    </v-card>

    <!-- Loading -->
    <div v-if="store.loading" class="d-flex justify-center py-12">
      <v-progress-circular indeterminate color="primary" />
    </div>

    <!-- Teams table -->
    <v-card
      v-if="!store.loading && visibleTeams.length > 0"
      color="surface"
      class="mb-8"
    >
      <v-table density="comfortable">
        <thead>
          <tr>
            <th>Name</th>
            <th>Members</th>
            <th>Repositories</th>
            <th>Status</th>
            <th style="width: 80px;">Actions</th>
          </tr>
        </thead>
        <tbody>
          <tr
            v-for="team in visibleTeams"
            :key="team.id"
            :class="{ 'opacity-50': team.status === 'archived' }"
          >
            <td>
              <div class="d-flex align-center ga-2 py-2">
                <v-avatar size="32" color="primary" variant="tonal">
                  <v-icon size="18">mdi-account-group-outline</v-icon>
                </v-avatar>
                <div>
                  <span class="font-weight-medium">{{ team.name }}</span>
                  <div
                    v-if="detailFor(team.id)?.description"
                    class="text-caption text-medium-emphasis"
                  >
                    {{ detailFor(team.id)?.description }}
                  </div>
                </div>
              </div>
            </td>
            <td>
              <div class="d-flex align-center ga-1">
                <template v-if="memberPreview(team.id).length > 0">
                  <v-avatar
                    v-for="m in memberPreview(team.id).slice(0, 3)"
                    :key="m.user_id"
                    size="24"
                    color="primary"
                    variant="tonal"
                    :title="m.name"
                  >
                    <span class="text-caption font-weight-bold">
                      {{ initials(m.name) }}
                    </span>
                  </v-avatar>
                  <v-chip
                    v-if="memberPreview(team.id).length > 3"
                    size="x-small"
                    variant="tonal"
                    class="ml-1"
                  >
                    +{{ memberPreview(team.id).length - 3 }}
                  </v-chip>
                </template>
                <span v-else class="text-caption text-medium-emphasis">No members</span>
              </div>
            </td>
            <td>
              <div class="d-flex flex-wrap ga-1">
                <template v-if="repoPreview(team.id).length > 0">
                  <v-chip
                    v-for="r in repoPreview(team.id).slice(0, 3)"
                    :key="r.repo_id"
                    size="x-small"
                    variant="tonal"
                  >
                    {{ r.name }}
                  </v-chip>
                  <v-chip
                    v-if="repoPreview(team.id).length > 3"
                    size="x-small"
                    variant="tonal"
                  >
                    +{{ repoPreview(team.id).length - 3 }}
                  </v-chip>
                </template>
                <span v-else class="text-caption text-medium-emphasis">No repos</span>
              </div>
            </td>
            <td>
              <v-chip
                :color="team.status === 'active' ? 'success' : 'warning'"
                size="small"
                variant="tonal"
              >
                {{ team.status === 'active' ? 'Active' : 'Archived' }}
              </v-chip>
            </td>
            <td>
              <div class="d-flex align-center">
                <v-tooltip location="top" content-class="text-white bg-grey-darken-3">
                  <template #activator="{ props }">
                    <v-btn
                      v-bind="props"
                      icon="mdi-pencil-outline"
                      size="small"
                      variant="text"
                      color="primary"
                      @click="openEdit(team.id)"
                    />
                  </template>
                  Edit members, repos, description
                </v-tooltip>
                <v-tooltip location="top" content-class="text-white bg-grey-darken-3">
                  <template #activator="{ props }">
                    <v-btn
                      v-bind="props"
                      :icon="
                        team.status === 'active'
                          ? 'mdi-archive-outline'
                          : 'mdi-archive-arrow-up-outline'
                      "
                      size="small"
                      variant="text"
                      :color="team.status === 'active' ? 'warning' : 'success'"
                      @click="toggleArchive(team.id)"
                    />
                  </template>
                  {{ team.status === 'active' ? 'Archive team' : 'Restore team' }}
                </v-tooltip>
              </div>
            </td>
          </tr>
        </tbody>
      </v-table>
    </v-card>

    <!-- Create dialog -->
    <v-dialog v-model="createOpen" max-width="480">
      <v-card>
        <v-card-title>New team</v-card-title>
        <v-card-text>
          <v-text-field
            v-model="newName"
            label="Name"
            variant="outlined"
            density="compact"
            autofocus
          />
          <v-textarea
            v-model="newDescription"
            label="Description (optional)"
            variant="outlined"
            density="compact"
            rows="2"
          />
        </v-card-text>
        <v-card-actions>
          <v-spacer />
          <v-btn variant="text" @click="createOpen = false">Cancel</v-btn>
          <v-btn color="primary" :disabled="!newName.trim()" @click="onCreate">
            Create
          </v-btn>
        </v-card-actions>
      </v-card>
    </v-dialog>

    <!-- Edit dialog -->
    <v-dialog v-model="editOpen" max-width="640">
      <v-card v-if="editingDetail">
        <v-card-title class="d-flex align-center ga-2">
          <v-icon icon="mdi-account-group-outline" />
          {{ editingDetail.name }}
        </v-card-title>
        <v-card-text>
          <v-textarea
            v-model="editingDescription"
            label="Description"
            variant="outlined"
            density="compact"
            rows="2"
            hide-details
            class="mb-4"
            @blur="onDescriptionBlur"
          />

          <div class="text-subtitle-2 font-weight-medium mb-2">Members</div>
          <v-chip-group column class="mb-2">
            <v-chip
              v-for="m in editingDetail.members"
              :key="m.user_id"
              closable
              size="small"
              variant="tonal"
              @click:close="onRemoveMember(m.user_id)"
            >
              <v-avatar start size="20" color="primary" variant="tonal">
                <span class="text-caption font-weight-bold">{{ initials(m.name) }}</span>
              </v-avatar>
              {{ m.name }}
              <span class="text-caption ml-2 text-medium-emphasis">{{ m.role }}</span>
            </v-chip>
            <span
              v-if="editingDetail.members.length === 0"
              class="text-caption text-medium-emphasis"
            >
              No members yet.
            </span>
          </v-chip-group>
          <v-autocomplete
            v-model="memberToAdd"
            :items="memberOptions"
            item-title="label"
            item-value="value"
            label="Add member…"
            variant="outlined"
            density="compact"
            hide-details
            class="mb-4"
            clearable
            @update:model-value="onAddMember"
          />

          <div class="text-subtitle-2 font-weight-medium mb-2">Repositories</div>
          <v-chip-group column class="mb-2">
            <v-chip
              v-for="r in editingDetail.repos"
              :key="r.repo_id"
              closable
              size="small"
              variant="tonal"
              @click:close="onRemoveRepo(r.repo_id)"
            >
              <v-icon start size="14">mdi-source-repository</v-icon>
              {{ r.name }}
            </v-chip>
            <span
              v-if="editingDetail.repos.length === 0"
              class="text-caption text-medium-emphasis"
            >
              No repos mapped yet.
            </span>
          </v-chip-group>
          <v-autocomplete
            v-model="repoToAdd"
            :items="repoOptions"
            item-title="label"
            item-value="value"
            label="Add repository…"
            variant="outlined"
            density="compact"
            hide-details
            clearable
            @update:model-value="onAddRepo"
          />
        </v-card-text>
        <v-card-actions>
          <v-spacer />
          <v-btn variant="text" @click="editOpen = false">Done</v-btn>
        </v-card-actions>
      </v-card>
    </v-dialog>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { useTeamsStore } from '@/stores/teams'
import { useMembersStore } from '@/stores/members'
import { useSettingsStore } from '@/stores/settings'

const store = useTeamsStore()
const membersStore = useMembersStore()
const settingsStore = useSettingsStore()

const statusFilter = ref<'active' | 'all'>('active')
const statusOptions = [
  { value: 'active', label: 'Active' },
  { value: 'all', label: 'All' },
]

const editingId = ref<string | null>(null)
const editingDescription = ref('')
const memberToAdd = ref<string | null>(null)
const repoToAdd = ref<string | null>(null)
const editOpen = ref(false)

const createOpen = ref(false)
const newName = ref('')
const newDescription = ref('')

const visibleTeams = computed(() =>
  statusFilter.value === 'active'
    ? store.teams.filter(t => t.status === 'active')
    : store.teams,
)

const editingDetail = computed(() =>
  editingId.value ? store.detailsById[editingId.value] || null : null,
)

function detailFor(id: string) {
  return store.detailsById[id] || null
}

// Member / repo previews fall back to the detail cache. The table
// load eagerly fetches every visible team's detail (see onMounted)
// so previews populate without per-row roundtrips.
function memberPreview(id: string) {
  return detailFor(id)?.members || []
}
function repoPreview(id: string) {
  return detailFor(id)?.repos || []
}

const memberOptions = computed(() => {
  const onTeam = new Set(editingDetail.value?.members.map(m => m.user_id) || [])
  return membersStore.members
    .filter(m => m.isActive && !onTeam.has(m.id))
    .map(m => ({ value: m.id, label: `${m.name} (${m.role})` }))
})

const repoOptions = computed(() => {
  const onTeam = new Set(editingDetail.value?.repos.map(r => r.repo_id) || [])
  return settingsStore.repos
    .filter(r => r.status === 'active' && !onTeam.has(r.id))
    .map(r => ({ value: r.id, label: r.name }))
})

function initials(name: string): string {
  return name
    .split(/\s+/)
    .filter(Boolean)
    .map(w => w[0]!.toUpperCase())
    .slice(0, 2)
    .join('')
}

async function loadPreviewDetails(): Promise<void> {
  // Lazily fill in any visible team's detail so the table can render
  // member avatars + repo chips. Skips ones already cached.
  await Promise.all(
    visibleTeams.value
      .filter(t => !store.detailsById[t.id])
      .map(t => store.fetchTeam(t.id)),
  )
}

watch(visibleTeams, () => {
  loadPreviewDetails()
})

watch(editingDetail, (d) => {
  editingDescription.value = d?.description || ''
})

async function onStatusFilterChange(v: 'active' | 'all'): Promise<void> {
  await store.fetchTeams(v === 'all')
}

function openCreate(): void {
  newName.value = ''
  newDescription.value = ''
  createOpen.value = true
}

async function onCreate(): Promise<void> {
  const created = await store.createTeam({
    name: newName.value.trim(),
    description: newDescription.value.trim() || null,
  })
  if (created) {
    createOpen.value = false
    openEdit(created.id)
  }
}

async function openEdit(id: string): Promise<void> {
  editingId.value = id
  editOpen.value = true
  if (!store.detailsById[id]) {
    await store.fetchTeam(id)
  }
}

async function onDescriptionBlur(): Promise<void> {
  if (!editingDetail.value) return
  const next = editingDescription.value.trim() || null
  if (next === (editingDetail.value.description || null)) return
  await store.updateTeam(editingDetail.value.id, { description: next })
}

async function toggleArchive(id: string): Promise<void> {
  const team = store.teams.find(t => t.id === id)
  if (!team) return
  if (team.status === 'active') {
    await store.archiveTeam(id)
  } else {
    await store.updateTeam(id, { status: 'active' })
  }
}

async function onAddMember(userId: string | null): Promise<void> {
  if (!userId || !editingDetail.value) return
  await store.addMember(editingDetail.value.id, userId)
  memberToAdd.value = null
}

async function onRemoveMember(userId: string): Promise<void> {
  if (!editingDetail.value) return
  await store.removeMember(editingDetail.value.id, userId)
}

async function onAddRepo(repoId: string | null): Promise<void> {
  if (!repoId || !editingDetail.value) return
  await store.addRepo(editingDetail.value.id, repoId)
  repoToAdd.value = null
}

async function onRemoveRepo(repoId: string): Promise<void> {
  if (!editingDetail.value) return
  await store.removeRepo(editingDetail.value.id, repoId)
}

onMounted(async () => {
  await Promise.all([
    store.fetchTeams(false),
    membersStore.members.length === 0
      ? membersStore.fetchMembers()
      : Promise.resolve(),
    settingsStore.repos.length === 0
      ? settingsStore.fetchRepos()
      : Promise.resolve(),
  ])
  await loadPreviewDetails()
})
</script>
