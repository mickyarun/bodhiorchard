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

<!-- Roles tab on the Members page: every role as a card, with creating,
     editing and deleting custom roles. Built-in roles are read-only. -->
<template>
  <div class="roles-tab">
    <div class="roles-tab__bar">
      <p class="roles-tab__note">Built-in roles are read-only. Create custom roles for your organization.</p>
      <v-btn color="primary" variant="flat" prepend-icon="mdi-plus" @click="openForm(null)">Create role</v-btn>
    </div>
    <AppCallout v-if="store.error" variant="error">
      {{ store.error }}
      <template #actions>
        <v-btn icon="mdi-close" variant="text" size="small" aria-label="Dismiss" @click="store.error = null" />
      </template>
    </AppCallout>
    <div class="roles-grid">
      <RoleCard v-for="role in store.roles" :key="role.id" :role="role" @edit="openForm" @delete="confirmDelete" />
    </div>

    <RoleFormDialog v-model="formOpen" :role="editing" />

    <v-dialog v-model="deleteOpen" max-width="400">
      <v-card>
        <v-card-title>Delete role</v-card-title>
        <v-card-text>
          Delete <strong>{{ deleting ? roleTitle(deleting.name) : '' }}</strong>? Members with this role will need
          a new one.
        </v-card-text>
        <v-card-actions class="px-4 pb-4">
          <v-spacer />
          <v-btn variant="text" @click="deleteOpen = false">Cancel</v-btn>
          <v-btn color="error" variant="flat" :loading="removing" @click="submitDelete">Delete</v-btn>
        </v-card-actions>
      </v-card>
    </v-dialog>
  </div>
</template>

<script setup lang="ts">
import { ref } from 'vue'
import AppCallout from '@/components/common/AppCallout.vue'
import RoleCard from './RoleCard.vue'
import RoleFormDialog from './RoleFormDialog.vue'
import { useMembersStore, type RoleOption } from '@/stores/members'
import { roleTitle } from '@/utils/members'

const store = useMembersStore()

const formOpen = ref(false)
const editing = ref<RoleOption | null>(null)
const deleteOpen = ref(false)
const deleting = ref<RoleOption | null>(null)
const removing = ref(false)

function openForm(role: RoleOption | null): void {
  editing.value = role
  formOpen.value = true
}

function confirmDelete(role: RoleOption): void {
  deleting.value = role
  deleteOpen.value = true
}

async function submitDelete(): Promise<void> {
  if (!deleting.value) return
  removing.value = true
  const ok = await store.deleteRole(deleting.value.id)
  removing.value = false
  if (ok) deleteOpen.value = false
}
</script>

<style scoped>
.roles-tab {
  display: flex;
  flex-direction: column;
  gap: 16px;
}
.roles-tab__bar {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
}
.roles-tab__note {
  margin: 0;
  font-size: 14px;
  color: rgb(var(--v-theme-on-surface-variant));
}
.roles-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(min(100%, 280px), 1fr));
  gap: 12px;
}
</style>
