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

<!-- The editable fields of the open bug: status, owner and linked feature.
     Each saves as soon as it changes; people without the permission see
     the value as text. -->
<template>
  <div class="bug-fields">
    <v-select
      :model-value="bug.status"
      :items="STATUS_OPTIONS"
      label="Status"
      :disabled="!canEditBugs"
      variant="outlined"
      density="compact"
      hide-details
      @update:model-value="save({ status: $event })"
    />

    <v-autocomplete
      v-if="canAssignBugs"
      :model-value="bug.assigneeId"
      :items="assigneeOptions"
      label="Owner"
      placeholder="Unassigned"
      persistent-placeholder
      variant="outlined"
      density="compact"
      hide-details
      clearable
      @update:model-value="save({ assigneeId: $event ?? null })"
    />

    <v-autocomplete
      v-if="canEditBugs"
      :model-value="bug.featureId"
      :items="featureOptions"
      :loading="featureSearchLoading"
      label="Feature"
      placeholder="Search features"
      persistent-placeholder
      no-filter
      variant="outlined"
      density="compact"
      hide-details
      clearable
      @update:search="onFeatureSearch"
      @update:model-value="save({ featureId: $event ?? null })"
    />
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { usePermissions } from '@/composables/usePermissions'
import { useBugsStore } from '@/stores/bugs'
import { useFeaturesStore } from '@/stores/features'
import { useMembersStore } from '@/stores/members'
import { BUG_BOARD_COLUMNS, BUG_STATUS_LABELS, type BugRead } from '@/types'

const props = defineProps<{ bug: BugRead }>()

const bugsStore = useBugsStore()
const featuresStore = useFeaturesStore()
const membersStore = useMembersStore()
const { canEditBugs, canAssignBugs } = usePermissions()

const STATUS_OPTIONS = BUG_BOARD_COLUMNS.map(value => ({ title: BUG_STATUS_LABELS[value], value }))

const assigneeOptions = computed(() => membersStore.members.map(m => ({ title: m.name || m.email, value: m.id })))

// The linked feature stays in the list even before a search, so its title shows.
const featureOptions = computed(() => {
  const options = featuresStore.items.map(f => ({ title: f.featureTitle, value: f.id }))
  const { featureId, featureTitle } = props.bug
  if (featureId && featureTitle && !options.some(o => o.value === featureId)) {
    options.unshift({ title: featureTitle, value: featureId })
  }
  return options
})

const featureSearchLoading = ref(false)
let featureSearchTimer: ReturnType<typeof setTimeout> | undefined

function onFeatureSearch(query: string): void {
  clearTimeout(featureSearchTimer)
  featureSearchTimer = setTimeout(async () => {
    featureSearchLoading.value = true
    await featuresStore.fetchPage({ q: query || undefined, mode: 'active' })
    featureSearchLoading.value = false
  }, 250)
}

async function save(body: Record<string, unknown>): Promise<void> {
  await bugsStore.updateBug(props.bug.id, body)
}

onMounted(() => {
  if (canAssignBugs.value && membersStore.members.length === 0) void membersStore.fetchMembers()
})
</script>

<style scoped>
.bug-fields {
  display: grid;
  gap: 14px;
}
</style>
