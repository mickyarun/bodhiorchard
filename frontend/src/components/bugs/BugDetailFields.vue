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
     Each saves as soon as it changes, except a move to resolved, closed or
     rejected, which asks first (those stamp the resolve time or settle QA
     SP). Fields people can't change are shown as text by the panel. -->
<template>
  <div class="bug-fields">
    <v-select
      v-if="canEditBugs"
      :model-value="bug.status"
      :items="STATUS_OPTIONS"
      label="Status"
      variant="outlined"
      density="compact"
      hide-details
      @update:model-value="changeStatus"
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

    <BugFeaturePicker
      v-if="canEditBugs"
      :model-value="bug.featureId"
      :current-title="bug.featureTitle"
      @update:model-value="save({ featureId: $event })"
    />

    <AppConfirmDialog
      :model-value="!!confirming"
      :title="confirming?.title ?? ''"
      :body="confirming?.body"
      :action="confirming?.action ?? ''"
      :busy="savingStatus"
      @update:model-value="!$event && (pendingStatus = null)"
      @confirm="confirmStatus"
    />
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import AppConfirmDialog from '@/components/common/AppConfirmDialog.vue'
import { useMemberDirectory } from '@/composables/useMemberDirectory'
import { usePermissions } from '@/composables/usePermissions'
import { BUG_BOARD_COLUMNS, BUG_STATUS_LABELS, type BugRead, type BugStatusValue } from '@/types'
import { statusConfirm } from '@/utils/bugList'
import BugFeaturePicker from './BugFeaturePicker.vue'

// ``save`` patches the bug and resolves true once it's saved.
const props = defineProps<{ bug: BugRead; save: (body: Record<string, unknown>) => Promise<boolean> }>()

// The directory, not the admin members list: assigning a bug needs
// bugs:assign, not team:manage, so most who can assign could not read it.
const directory = useMemberDirectory()
const { canEditBugs, canAssignBugs } = usePermissions()

const STATUS_OPTIONS = BUG_BOARD_COLUMNS.map(value => ({ title: BUG_STATUS_LABELS[value], value }))

const assigneeOptions = computed(() => directory.entries.value.map(m => ({ title: m.name || m.email, value: m.id })))

function save(body: Record<string, unknown>): void {
  void props.save(body)
}

// The select stays on the bug's saved status until a confirmed move saves.
const pendingStatus = ref<BugStatusValue | null>(null)
const confirming = computed(() => (pendingStatus.value ? statusConfirm(pendingStatus.value) : null))
const savingStatus = ref(false)

function changeStatus(status: BugStatusValue): void {
  if (statusConfirm(status)) pendingStatus.value = status
  else save({ status })
}

async function confirmStatus(): Promise<void> {
  if (!pendingStatus.value) return
  savingStatus.value = true
  const ok = await props.save({ status: pendingStatus.value })
  savingStatus.value = false
  if (ok) pendingStatus.value = null
}

onMounted(() => {
  if (canAssignBugs.value) void directory.ensureLoaded()
})
</script>

<style scoped>
.bug-fields {
  display: grid;
  gap: 14px;
}
</style>
