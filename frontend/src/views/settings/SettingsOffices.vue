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

<!-- Settings → Offices (employees:manage): the places people work from.
     Each can carry a leave policy, which people placed there move onto. -->
<template>
  <div class="pa-6 settings-offices">
    <div class="d-flex align-start justify-space-between flex-wrap ga-3 mb-6">
      <div>
        <h1 class="text-h5 font-weight-bold bo-display">Offices</h1>
        <p class="text-body-2 text-medium-emphasis">
          Where people work from. Set each person's office or remote status on their Employment tab.
        </p>
      </div>
      <v-btn color="primary" prepend-icon="mdi-plus" @click="edit(null)">Add office</v-btn>
    </div>

    <v-progress-linear v-if="store.loading && !store.offices.length" indeterminate color="primary" class="mb-4" />
    <AppCallout v-if="store.error" variant="error" class="mb-4">{{ store.error }}</AppCallout>
    <AppCallout v-if="actionError" variant="error" class="mb-4">{{ actionError }}</AppCallout>

    <LeaveEmptyState
      v-if="!store.loading && !store.offices.length && !store.error"
      icon="mdi-office-building-outline"
      title="No offices yet"
      body="Add one for each place people work from, with the leave policy they follow there."
    />
    <v-card v-else-if="store.offices.length" color="surface" rounded="lg">
      <v-table density="comfortable">
        <thead>
          <tr>
            <th>Office</th>
            <th>Leave policy</th>
            <th class="text-end">People</th>
            <th class="actions-col"><span class="d-sr-only">Actions</span></th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="office in store.offices" :key="office.id">
            <td>
              <div class="font-weight-medium">{{ office.name }}</div>
              <div class="text-caption text-medium-emphasis">{{ placeLine(office) }}</div>
            </td>
            <td>{{ office.leave_policy_name ?? 'None' }}</td>
            <td class="text-end">{{ office.employee_count }}</td>
            <td class="text-end">
              <v-btn icon="mdi-pencil-outline" variant="text" size="small" :aria-label="`Edit ${office.name}`" @click="edit(office)" />
              <v-btn
                icon="mdi-delete-outline"
                variant="text"
                size="small"
                :disabled="office.employee_count > 0"
                :title="office.employee_count > 0 ? 'Move its people to another office first' : undefined"
                :aria-label="`Delete ${office.name}`"
                :loading="busyId === office.id"
                @click="deleting = office"
              />
            </td>
          </tr>
        </tbody>
      </v-table>
    </v-card>

    <OfficeDialog v-model="dialogOpen" :office="editing" />
    <ConfirmDialog
      :model-value="!!deleting"
      title="Delete this office?"
      :message="`${deleting?.name ?? ''} will be removed. Nobody works from it.`"
      confirm-label="Delete office"
      icon="mdi-delete-outline"
      @update:model-value="value => !value && (deleting = null)"
      @confirm="remove"
    />
  </div>
</template>

<script setup lang="ts">
import { onMounted, ref } from 'vue'
import AppCallout from '@/components/common/AppCallout.vue'
import LeaveEmptyState from '@/components/leave/settings/LeaveEmptyState.vue'
import OfficeDialog from '@/components/people/offices/OfficeDialog.vue'
import ConfirmDialog from '@/components/settings/code/ConfirmDialog.vue'
import { useOfficesStore } from '@/stores/offices'
import type { OfficeRead } from '@/types/office'

const store = useOfficesStore()
const dialogOpen = ref(false)
const editing = ref<OfficeRead | null>(null)
const busyId = ref<string | null>(null)
const deleting = ref<OfficeRead | null>(null)
const actionError = ref('')

function placeLine(office: OfficeRead): string {
  return [office.city, office.country_code].filter(Boolean).join(', ') || 'No city set'
}

function edit(office: OfficeRead | null): void {
  editing.value = office
  dialogOpen.value = true
}

async function remove(): Promise<void> {
  const office = deleting.value
  deleting.value = null
  if (!office) return
  busyId.value = office.id
  actionError.value = (await store.deleteOffice(office.id)) ?? ''
  busyId.value = null
}

onMounted(() => void store.fetchOffices())
</script>

<style scoped>
.settings-offices {
  max-width: 960px;
}
.actions-col {
  width: 112px;
}
</style>
