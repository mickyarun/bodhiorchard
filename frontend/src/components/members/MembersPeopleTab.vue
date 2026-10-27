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

<!-- People tab on the Members page: the active/inactive filter, the
     people table and the per-person dialogs it opens. -->
<template>
  <div class="people-tab">
    <v-select
      v-model="statusFilter"
      :items="memberStatusOptions(store.members)"
      label="Show"
      density="compact"
      hide-details
      variant="outlined"
      class="people-tab__filter"
    />
    <div v-if="store.loading" class="d-flex justify-center py-12">
      <v-progress-circular indeterminate color="primary" aria-label="Loading members" />
    </div>
    <MembersPeopleTable
      v-else
      :members="filterMembersByStatus(store.members, statusFilter)"
      :roles="store.roles"
      @set-password="openPassword"
      @merge="openMerge"
      @unlink="openUnlink"
    />

    <SetPasswordDialog v-model="passwordOpen" :member="selected" />
    <MergeMembersDialog v-model="mergeOpen" :initial-target-id="selected?.id" />
    <UnlinkAliasDialog v-model="unlinkOpen" :member="selected" :email="alias" />
  </div>
</template>

<script setup lang="ts">
import { ref } from 'vue'
import MembersPeopleTable from './MembersPeopleTable.vue'
import MergeMembersDialog from './MergeMembersDialog.vue'
import SetPasswordDialog from './SetPasswordDialog.vue'
import UnlinkAliasDialog from './UnlinkAliasDialog.vue'
import { useMembersStore, type Member } from '@/stores/members'
import { filterMembersByStatus, memberStatusOptions, type MemberStatusFilter } from '@/utils/members'

const store = useMembersStore()

const statusFilter = ref<MemberStatusFilter>('active')
const selected = ref<Member | null>(null)
const alias = ref('')
const passwordOpen = ref(false)
const mergeOpen = ref(false)
const unlinkOpen = ref(false)

function openPassword(member: Member): void {
  selected.value = member
  passwordOpen.value = true
}

function openMerge(member: Member): void {
  selected.value = member
  mergeOpen.value = true
}

function openUnlink(member: Member, email: string): void {
  selected.value = member
  alias.value = email
  unlinkOpen.value = true
}
</script>

<style scoped>
.people-tab {
  display: flex;
  flex-direction: column;
  gap: 16px;
}
.people-tab__filter {
  max-width: 200px;
}
</style>
