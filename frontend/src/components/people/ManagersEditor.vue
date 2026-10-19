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

<!-- Reporting managers. An employee can have several; any one of them
     approves leave, and the primary is the one shown in the directory. -->
<template>
  <section>
    <div class="d-flex align-center justify-space-between mb-2">
      <h2 class="text-subtitle-1 font-weight-bold">Reporting managers</h2>
      <v-btn
        v-if="editable && !editing"
        variant="text"
        size="small"
        prepend-icon="mdi-pencil-outline"
        @click="startEdit"
      >
        Change
      </v-btn>
    </div>

    <template v-if="!editing">
      <p v-if="managers.length === 0" class="text-body-2 text-medium-emphasis">
        No manager set. Leave requests from {{ employeeName }} go to HR.
      </p>
      <div v-for="m in managers" :key="m.user_id" class="d-flex align-center ga-2 py-1">
        <span class="text-body-2">{{ m.name }}</span>
        <v-chip v-if="m.is_primary" size="x-small" label variant="tonal" color="primary">
          Primary
        </v-chip>
        <v-chip v-if="!m.is_active" size="x-small" label variant="tonal">Deactivated</v-chip>
      </div>
    </template>

    <template v-else>
      <v-radio-group v-model="primaryId" hide-details density="compact" class="mb-2">
        <div v-for="m in draft" :key="m.user_id" class="d-flex align-center ga-2">
          <v-radio :value="m.user_id" :label="labelFor(m.user_id)" />
          <v-spacer />
          <v-btn
            icon="mdi-close"
            variant="text"
            size="x-small"
            :aria-label="`Remove ${labelFor(m.user_id)}`"
            @click="remove(m.user_id)"
          />
        </div>
      </v-radio-group>
      <v-autocomplete
        v-model="adding"
        v-model:search="search"
        :items="addable"
        item-title="name"
        item-value="id"
        label="Add a manager"
        variant="outlined"
        density="compact"
        hide-details
        clearable
        class="mb-2"
        @update:model-value="add"
      />
      <p class="text-caption text-medium-emphasis mb-3">
        Any of these people can approve leave. The selected one is the primary.
      </p>
      <AppCallout v-if="error" variant="error" class="mb-3">{{ error }}</AppCallout>
      <div class="d-flex justify-end ga-2">
        <v-btn variant="text" @click="editing = false">Cancel</v-btn>
        <v-btn color="primary" :loading="saving" @click="save">Save managers</v-btn>
      </div>
    </template>
  </section>
</template>

<script setup lang="ts">
import { computed, nextTick, ref } from 'vue'
import AppCallout from '@/components/common/AppCallout.vue'
import { useMemberDirectory } from '@/composables/useMemberDirectory'
import { useEmployeesStore } from '@/stores/employees'
import type { ManagerInput, ManagerRef } from '@/types/employee'
import { normalizeManagers, setPrimary } from '@/utils/employee'

const props = defineProps<{
  employeeId: string
  employeeName: string
  managers: ManagerRef[]
  editable: boolean
}>()

const store = useEmployeesStore()
const { entries, ensureLoaded, nameFor } = useMemberDirectory()

const editing = ref(false)
const saving = ref(false)
const error = ref('')
const draft = ref<ManagerInput[]>([])
const adding = ref<string | null>(null)
const search = ref('')

const primaryId = computed({
  get: () => draft.value.find(m => m.is_primary)?.user_id ?? null,
  set: (id: string | null) => {
    if (id) draft.value = setPrimary(draft.value, id)
  },
})

const addable = computed(() =>
  entries.value.filter(
    e => e.id !== props.employeeId && !draft.value.some(m => m.user_id === e.id),
  ),
)

// Current managers come with their names (and whether they've left)
// from the record; the member directory only lists active members.
function labelFor(userId: string): string {
  const known = props.managers.find(m => m.user_id === userId)
  if (known) return known.is_active ? known.name : `${known.name} (deactivated)`
  return nameFor(userId)
}

async function startEdit(): Promise<void> {
  await ensureLoaded()
  draft.value = props.managers.map(m => ({ user_id: m.user_id, is_primary: m.is_primary }))
  error.value = ''
  editing.value = true
}

function add(userId: string | null): void {
  if (!userId) return
  draft.value = normalizeManagers([...draft.value, { user_id: userId, is_primary: false }])
  // Clear the picker once its own update has finished, or it keeps the
  // last name (and its search text) and the next pick misfires.
  void nextTick(() => {
    adding.value = null
    search.value = ''
  })
}

function remove(userId: string): void {
  draft.value = normalizeManagers(draft.value.filter(m => m.user_id !== userId))
}

async function save(): Promise<void> {
  saving.value = true
  error.value = (await store.updateManagers(props.employeeId, draft.value)) ?? ''
  saving.value = false
  if (!error.value) editing.value = false
}
</script>
