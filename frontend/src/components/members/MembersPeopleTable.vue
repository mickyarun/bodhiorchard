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

<!-- The people with access to the workspace: who they are, their role
     (changed in place), whether they are active, when they joined, and a
     menu for password, merge and deactivate. -->
<template>
  <section class="m-table" aria-label="People">
    <div class="m-table__scroll">
      <table>
        <thead>
          <tr>
            <th scope="col">Person</th>
            <th scope="col">Role</th>
            <th scope="col" class="m-table__wide">Status</th>
            <th scope="col" class="m-table__wide">Joined</th>
            <th scope="col"><span class="d-sr-only">Actions</span></th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="member in members" :key="member.id" :class="{ 'm-table__inactive': !member.isActive }">
            <td><MemberPersonCell :member="member" @unlink="email => emit('unlink', member, email)" /></td>
            <td>
              <v-select
                v-if="roles.length > 0"
                :model-value="member.roleId"
                :items="roleItems(roles)"
                :aria-label="`Role for ${member.name}`"
                density="compact"
                variant="outlined"
                hide-details
                class="role-select"
                :disabled="!member.isActive"
                @update:model-value="(id: string) => store.assignRole(member.id, id)"
              />
              <span v-else>{{ roleTitle(member.roleName || member.role) }}</span>
            </td>
            <td class="m-table__wide">
              <span class="m-status" :class="{ 'm-status--on': member.isActive }">{{ member.isActive ? 'Active' : 'Inactive' }}</span>
            </td>
            <td class="m-table__wide m-table__muted">{{ formatDate(member.createdAt) }}</td>
            <td>
              <v-menu location="bottom end">
                <template #activator="{ props: menu }">
                  <v-btn v-bind="menu" icon="mdi-dots-horizontal" variant="text" size="small" :aria-label="`More for ${member.name}`" />
                </template>
                <v-list density="compact">
                  <v-list-item :disabled="!member.isActive" prepend-icon="mdi-key-outline" title="Set password" @click="emit('set-password', member)" />
                  <v-list-item prepend-icon="mdi-account-arrow-right-outline" title="Merge into another member" @click="emit('merge', member)" />
                  <v-list-item
                    :prepend-icon="member.isActive ? 'mdi-account-off-outline' : 'mdi-account-check-outline'"
                    :title="member.isActive ? 'Deactivate' : 'Reactivate'"
                    @click="store.toggleMemberStatus(member.id)"
                  />
                </v-list>
              </v-menu>
            </td>
          </tr>
          <tr v-if="members.length === 0">
            <td colspan="5" class="m-table__empty">Nobody here.</td>
          </tr>
        </tbody>
      </table>
    </div>
  </section>
</template>

<script setup lang="ts">
import MemberPersonCell from './MemberPersonCell.vue'
import { useMembersStore, type Member, type RoleOption } from '@/stores/members'
import { formatDate } from '@/utils/date'
import { roleItems, roleTitle } from '@/utils/members'

defineProps<{ members: Member[]; roles: RoleOption[] }>()
const emit = defineEmits<{
  'set-password': [Member]
  merge: [Member]
  unlink: [Member, string]
}>()
const store = useMembersStore()
</script>

<style scoped src="./membersTable.css"></style>
<style scoped>
.role-select {
  min-width: 150px;
  max-width: 200px;
}
@media (max-width: 600px) {
  .role-select {
    min-width: 0;
    width: 100%;
    max-width: 136px;
  }
  .role-select :deep(.v-field__input) {
    font-size: 13px;
    padding-inline: 10px 0;
  }
}
</style>
