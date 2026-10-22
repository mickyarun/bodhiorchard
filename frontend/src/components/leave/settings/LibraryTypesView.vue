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
    <v-progress-linear v-if="store.loading && !store.entries.length" indeterminate color="primary" class="mb-4" />
    <LeaveEmptyState
      v-if="!store.loading && !store.entries.length && !store.error"
      icon="mdi-bookshelf"
      title="No library types yet"
      body="Add the types most policies share, such as earned, sick or casual leave."
    />
    <v-table v-else-if="store.entries.length" density="comfortable" hover class="library">
      <thead>
        <tr>
          <th scope="col">Leave type</th>
          <th scope="col">Default allowance</th>
          <th scope="col">Policies</th>
          <th scope="col"><span class="d-sr-only">Edit</span></th>
        </tr>
      </thead>
      <tbody>
        <tr
          v-for="entry in store.entries"
          :key="entry.id"
          class="library__row"
          tabindex="0"
          :aria-label="`Edit ${entry.name}`"
          @click="edit(entry)"
          @keydown.enter.prevent="edit(entry)"
          @keydown.space.prevent="edit(entry)"
        >
          <td>
            <span class="dot" aria-hidden="true" :style="{ background: `rgb(var(--v-theme-${swatchColor(entry.color_key)}))` }" />
            <span class="font-weight-medium">{{ entry.name }}</span>
            <div v-if="typeRuleTags(entry).length" class="tags">
              <v-chip v-for="tag in typeRuleTags(entry)" :key="tag" size="x-small" variant="outlined" label>{{ tag }}</v-chip>
            </div>
          </td>
          <td>{{ allowanceLabel(entry) }}</td>
          <td>
            <div class="text-body-2">{{ usesLabel(entry.uses) }}</div>
            <div v-if="entry.uses.length" class="tags tags--flush">
              <v-chip v-for="use in entry.uses" :key="use.type_id" size="x-small" variant="tonal" label>{{ useLabel(use) }}</v-chip>
            </div>
          </td>
          <td class="text-right">
            <v-icon icon="mdi-chevron-right" size="20" class="text-medium-emphasis" aria-hidden="true" />
          </td>
        </tr>
      </tbody>
    </v-table>
    <LeaveTypeDialog
      v-model="dialogOpen"
      library
      :initial="editing && entryDraft(editing)"
      :scope="editing?.uses.length ? 'on every policy that uses it' : 'on the policies you add it to'"
      :note="editNote"
      :save="save"
    />
  </section>
</template>

<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import AppCallout from '@/components/common/AppCallout.vue'
import LeaveEmptyState from '@/components/leave/settings/LeaveEmptyState.vue'
import LeaveTypeDialog from '@/components/leave/settings/LeaveTypeDialog.vue'
import { useLeaveLibraryStore } from '@/stores/leaveLibrary'
import type { LibraryTypeRead } from '@/types/leaveLibrary'
import type { LeaveTypeWrite } from '@/types/leavePolicy'
import { swatchColor } from '@/utils/leave'
import { entryBody, entryDraft, useLabel, usesLabel } from '@/utils/leaveLibrary'
import { allowanceLabel, typeRuleTags } from '@/utils/leavePolicyDisplay'

const store = useLeaveLibraryStore()
const route = useRoute()
const router = useRouter()
const dialogOpen = ref(false)
const editing = ref<LibraryTypeRead | null>(null)

const editNote = computed(() => {
  const uses = editing.value?.uses ?? []
  if (!uses.length) return ''
  const names = uses.map(u => u.policy_name).join(', ')
  return `Saving updates it on ${names}. Policies with their own quota keep it.`
})

function edit(entry: LibraryTypeRead | null): void {
  editing.value = entry
  dialogOpen.value = true
}

function save(body: LeaveTypeWrite): Promise<string | null> {
  return store.saveEntry(entryBody(body), editing.value?.id ?? null)
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
.library {
  background: transparent;
}
.library__row {
  cursor: pointer;
}
.library__row:focus-visible {
  outline: 2px solid rgb(var(--v-theme-primary));
  outline-offset: -2px;
}
.tags {
  display: flex;
  flex-wrap: wrap;
  gap: 4px;
  margin: 4px 0 2px 20px;
}
.tags--flush {
  margin-left: 0;
}
.dot {
  display: inline-block;
  width: 10px;
  height: 10px;
  border-radius: 50%;
  margin-right: 10px;
}
</style>
