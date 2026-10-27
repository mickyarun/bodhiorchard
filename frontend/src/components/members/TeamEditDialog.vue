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

<!-- Edit one team: its description (saved on blur), its members and the
     repositories it owns. Every change saves as it is made. -->
<template>
  <v-dialog v-model="open" max-width="640">
    <v-card v-if="detail">
      <v-card-title class="d-flex align-center justify-space-between">
        <span>{{ detail.name }}</span>
        <v-btn icon="mdi-close" variant="text" size="small" aria-label="Close" @click="open = false" />
      </v-card-title>
      <v-card-text>
        <v-textarea
          v-model="description"
          label="Description"
          variant="outlined"
          density="compact"
          rows="2"
          hide-details
          class="mb-4"
          @blur="saveDescription"
        />

        <div class="text-subtitle-2 mb-2">Members</div>
        <v-chip-group column class="mb-2">
          <v-chip
            v-for="m in detail.members"
            :key="m.user_id"
            closable
            size="small"
            variant="tonal"
            :close-label="`Remove ${m.name}`"
            @click:close="store.removeMember(detail.id, m.user_id)"
          >
            {{ m.name }}<span class="text-caption ml-2 text-medium-emphasis">{{ roleTitle(m.role) }}</span>
          </v-chip>
          <span v-if="detail.members.length === 0" class="text-caption text-medium-emphasis">No members yet.</span>
        </v-chip-group>
        <v-autocomplete
          v-model="memberToAdd"
          :items="memberOptions"
          label="Add a member"
          variant="outlined"
          density="compact"
          hide-details
          clearable
          class="mb-4"
          @update:model-value="addMember"
        />

        <div class="text-subtitle-2 mb-2">Repositories</div>
        <v-chip-group column class="mb-2">
          <v-chip
            v-for="r in detail.repos"
            :key="r.repo_id"
            closable
            size="small"
            variant="tonal"
            prepend-icon="mdi-source-repository"
            :close-label="`Remove ${r.name}`"
            @click:close="store.removeRepo(detail.id, r.repo_id)"
          >
            {{ r.name }}
          </v-chip>
          <span v-if="detail.repos.length === 0" class="text-caption text-medium-emphasis">No repositories yet.</span>
        </v-chip-group>
        <v-autocomplete
          v-model="repoToAdd"
          :items="repoOptions"
          label="Add a repository"
          variant="outlined"
          density="compact"
          hide-details
          clearable
          @update:model-value="addRepo"
        />
      </v-card-text>
      <v-card-actions class="px-4 pb-4">
        <v-spacer />
        <v-btn variant="text" @click="open = false">Done</v-btn>
      </v-card-actions>
    </v-card>
  </v-dialog>
</template>

<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { useMembersStore } from '@/stores/members'
import { useSettingsStore } from '@/stores/settings'
import { useTeamsStore } from '@/stores/teams'
import { roleTitle } from '@/utils/members'

const props = defineProps<{ teamId: string | null }>()
const open = defineModel<boolean>({ required: true })

const store = useTeamsStore()
const membersStore = useMembersStore()
const settingsStore = useSettingsStore()

const description = ref('')
const memberToAdd = ref<string | null>(null)
const repoToAdd = ref<string | null>(null)

const detail = computed(() => (props.teamId ? store.detailsById[props.teamId] || null : null))

watch(detail, d => {
  description.value = d?.description || ''
}, { immediate: true })

const memberOptions = computed(() => {
  const onTeam = new Set(detail.value?.members.map(m => m.user_id) || [])
  return membersStore.members
    .filter(m => m.isActive && !onTeam.has(m.id))
    .map(m => ({ value: m.id, title: `${m.name} (${roleTitle(m.role)})` }))
})

const repoOptions = computed(() => {
  const onTeam = new Set(detail.value?.repos.map(r => r.repo_id) || [])
  return settingsStore.repos
    .filter(r => r.status === 'active' && !onTeam.has(r.id))
    .map(r => ({ value: r.id, title: r.name }))
})

async function saveDescription(): Promise<void> {
  if (!detail.value) return
  const next = description.value.trim() || null
  if (next === (detail.value.description || null)) return
  await store.updateTeam(detail.value.id, { description: next })
}

async function addMember(userId: string | null): Promise<void> {
  if (!userId || !detail.value) return
  await store.addMember(detail.value.id, userId)
  memberToAdd.value = null
}

async function addRepo(repoId: string | null): Promise<void> {
  if (!repoId || !detail.value) return
  await store.addRepo(detail.value.id, repoId)
  repoToAdd.value = null
}
</script>
