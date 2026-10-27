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

<!-- Teams list: name and description, a preview of members and owned
     repositories, status, and edit / archive actions. -->
<template>
  <section class="m-table" aria-label="Teams">
    <div class="m-table__scroll">
      <table>
        <thead>
          <tr>
            <th scope="col">Team</th>
            <th scope="col" class="m-table__wide">Members</th>
            <th scope="col" class="m-table__wide">Repositories</th>
            <th scope="col">Status</th>
            <th scope="col"><span class="d-sr-only">Actions</span></th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="team in teams" :key="team.id" :class="{ 'm-table__inactive': team.status === 'archived' }">
            <td>
              <span class="m-table__name">{{ team.name }}</span>
              <div v-if="detailFor(team.id)?.description" class="m-table__sub">{{ detailFor(team.id)?.description }}</div>
            </td>
            <td class="m-table__wide">
              <span v-if="membersOf(team.id).length" class="stack">
                <AppMonogram v-for="m in membersOf(team.id).slice(0, 3)" :key="m.user_id" :name="m.name" :size="26" :title="m.name" />
                <span v-if="membersOf(team.id).length > 3" class="m-table__sub">+{{ membersOf(team.id).length - 3 }}</span>
              </span>
              <span v-else class="m-table__sub">No members</span>
            </td>
            <td class="m-table__wide">
              <span class="m-table__sub">{{ repoLine(team.id) }}</span>
            </td>
            <td>
              <span class="m-status" :class="{ 'm-status--on': team.status === 'active' }">
                {{ team.status === 'active' ? 'Active' : 'Archived' }}
              </span>
            </td>
            <td class="actions">
              <v-btn icon="mdi-pencil-outline" size="small" variant="text" :aria-label="`Edit ${team.name}`" title="Edit members, repositories and description" @click="emit('edit', team.id)" />
              <v-btn
                :icon="team.status === 'active' ? 'mdi-archive-outline' : 'mdi-archive-arrow-up-outline'"
                size="small"
                variant="text"
                :aria-label="`${team.status === 'active' ? 'Archive' : 'Restore'} ${team.name}`"
                :title="team.status === 'active' ? 'Archive team' : 'Restore team'"
                @click="emit('archive', team.id)"
              />
            </td>
          </tr>
          <tr v-if="teams.length === 0">
            <td colspan="5" class="m-table__empty">No teams to show.</td>
          </tr>
        </tbody>
      </table>
    </div>
  </section>
</template>

<script setup lang="ts">
import AppMonogram from '@/components/common/AppMonogram.vue'
import { useTeamsStore, type TeamSummary } from '@/stores/teams'

const REPO_PREVIEW = 3

defineProps<{ teams: TeamSummary[] }>()
const emit = defineEmits<{ edit: [string]; archive: [string] }>()
const store = useTeamsStore()

function detailFor(id: string) {
  return store.detailsById[id] || null
}

function membersOf(id: string) {
  return detailFor(id)?.members || []
}

function repoLine(id: string): string {
  const repos = detailFor(id)?.repos || []
  if (repos.length === 0) return 'No repositories'
  const names = repos.slice(0, REPO_PREVIEW).map(r => r.name).join(', ')
  return repos.length > REPO_PREVIEW ? `${names} +${repos.length - REPO_PREVIEW}` : names
}
</script>

<style scoped src="./membersTable.css"></style>
<style scoped>
.stack {
  display: inline-flex;
  align-items: center;
  gap: 4px;
}
.actions {
  white-space: nowrap;
  text-align: right;
}
</style>
