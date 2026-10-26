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

<!-- Settings → Leave → Leave types: the org's library. A type is defined once
     here and added to policies; editing it updates every policy that uses it
     (each keeps its own quota if it set one). `?entry=<id>` opens one. -->
<template>
  <section aria-label="Leave type library">
    <div class="d-flex align-start justify-space-between flex-wrap ga-3 mb-4">
      <p class="text-body-2 text-medium-emphasis intro">
        Define a leave type once and add it to any policy. Changing it here changes it on every
        policy that uses it; a policy can keep its own yearly quota.
      </p>
      <v-btn color="primary" variant="tonal" prepend-icon="mdi-plus" @click="edit(null)">Add library type</v-btn>
    </div>
    <AppCallout v-if="store.error" variant="error" class="mb-4">{{ store.error }}</AppCallout>
    <AppCallout v-if="deleteError" variant="error" class="mb-4">{{ deleteError }}</AppCallout>
    <v-progress-linear v-if="store.loading && !store.entries.length" indeterminate color="primary" class="mb-4" />
    <LeaveEmptyState
      v-if="!store.loading && !store.entries.length && !store.error"
      icon="mdi-bookshelf"
      title="No library types yet"
      body="Add the types most policies share, such as earned, sick or casual leave."
    />
    <LibraryTypeTable v-else-if="store.entries.length" :entries="store.entries" @edit="edit" />
    <LeaveTypeDialog
      v-model="dialogOpen"
      library
      :initial="editing && entryDraft(editing)"
      :scope="editing?.uses.length ? 'on every policy that uses it' : 'on the policies you add it to'"
      :note="editNote"
      :save="save"
    >
      <template v-if="editing" #actions>
        <v-btn v-if="!editing.uses.length" variant="text" color="error" @click="deleting = editing">Delete</v-btn>
        <span v-else class="text-caption text-medium-emphasis">To delete it, stop following it on each policy first.</span>
      </template>
    </LeaveTypeDialog>
    <ConfirmDialog
      :model-value="!!deleting"
      title="Delete this library type?"
      :message="`${deleting?.name ?? ''} isn't on any policy. Its history stays.`"
      confirm-label="Delete"
      icon="mdi-delete-outline"
      @update:model-value="value => !value && (deleting = null)"
      @confirm="remove"
    />
    <LibraryHistory />
  </section>
</template>

<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import AppCallout from '@/components/common/AppCallout.vue'
import LeaveEmptyState from '@/components/leave/settings/LeaveEmptyState.vue'
import LeaveTypeDialog from '@/components/leave/settings/LeaveTypeDialog.vue'
import LibraryHistory from '@/components/leave/settings/LibraryHistory.vue'
import LibraryTypeTable from '@/components/leave/settings/LibraryTypeTable.vue'
import ConfirmDialog from '@/components/settings/code/ConfirmDialog.vue'
import { useLeaveLibraryStore } from '@/stores/leaveLibrary'
import type { LibraryTypeRead } from '@/types/leaveLibrary'
import type { LeaveTypeWrite } from '@/types/leavePolicy'
import { entryBody, entryDraft } from '@/utils/leaveLibrary'

const store = useLeaveLibraryStore()
const route = useRoute()
const router = useRouter()
const dialogOpen = ref(false)
const editing = ref<LibraryTypeRead | null>(null)
const deleting = ref<LibraryTypeRead | null>(null)
const deleteError = ref('')

const editNote = computed(() => {
  const uses = editing.value?.uses ?? []
  if (!uses.length) return ''
  const names = uses.map(u => u.policy_name).join(', ')
  return `Saving updates it on ${names}. Policies with their own quota keep it.`
})

function edit(entry: LibraryTypeRead | null): void {
  deleteError.value = ''
  editing.value = entry
  dialogOpen.value = true
}

function save(body: LeaveTypeWrite): Promise<string | null> {
  return store.saveEntry(entryBody(body), editing.value?.id ?? null)
}

async function remove(): Promise<void> {
  const entry = deleting.value
  deleting.value = null
  if (!entry) return
  dialogOpen.value = false
  deleteError.value = (await store.deleteEntry(entry.id)) ?? ''
}

// Opened from a policy's "Edit in library": show that entry, then drop it from the URL.
watch(
  () => [route.query.entry, store.entries] as const,
  ([id, entries]) => {
    const entry = entries.find(e => e.id === id)
    if (!entry) return
    edit(entry)
    const { entry: _entry, ...rest } = route.query
    void router.replace({ query: rest })
  },
)

onMounted(() => {
  void store.fetchEntries()
})
</script>

<style scoped>
.intro {
  max-width: 640px;
}
</style>
