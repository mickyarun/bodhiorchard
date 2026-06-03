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

<template>
  <v-card v-if="bugsStore.currentBug" color="surface" class="pa-6" flat>
    <div class="d-flex align-center ga-2 mb-3">
      <v-chip
        :color="BUG_SEVERITY_COLORS[bugsStore.currentBug.severity]"
        size="small"
        variant="tonal"
      >
        {{ bugsStore.currentBug.severity }}
      </v-chip>
      <v-chip
        :color="bugsStore.currentBug.bugType === 'production' ? 'error' : 'info'"
        size="small"
        variant="tonal"
      >
        {{ bugsStore.currentBug.bugType }}
      </v-chip>
      <v-spacer />
      <v-btn icon="mdi-close" variant="text" size="small" @click="$emit('close')" />
    </div>

    <!-- Title (inline-edit) -->
    <div v-if="editingTitle" class="mb-2 d-flex ga-2">
      <v-text-field
        v-model="titleDraft"
        variant="outlined"
        density="compact"
        hide-details
        autofocus
      />
      <v-btn icon="mdi-check" size="small" color="primary" @click="saveTitle" />
      <v-btn icon="mdi-close" size="small" variant="text" @click="cancelTitle" />
    </div>
    <div
      v-else
      class="text-h6 font-weight-bold mb-2"
      :class="{ 'cursor-pointer': canEditBugs }"
      @click="canEditBugs && startEditTitle()"
    >
      {{ bugsStore.currentBug.title }}
    </div>

    <!-- Description -->
    <div v-if="editingDescription" class="mb-3 d-flex flex-column ga-2">
      <v-textarea
        v-model="descriptionDraft"
        variant="outlined"
        density="compact"
        rows="4"
        hide-details
        autofocus
      />
      <div class="d-flex ga-2 justify-end">
        <v-btn variant="text" size="small" @click="cancelDescription">Cancel</v-btn>
        <v-btn color="primary" variant="flat" size="small" @click="saveDescription">Save</v-btn>
      </div>
    </div>
    <div
      v-else
      class="text-body-2 mb-4"
      :class="{ 'cursor-pointer text-medium-emphasis': !bugsStore.currentBug.description }"
      style="white-space: pre-wrap;"
      @click="canEditBugs && startEditDescription()"
    >
      {{ bugsStore.currentBug.description || (canEditBugs ? 'Add a description…' : 'No description') }}
    </div>

    <!-- Status -->
    <div class="mb-4">
      <div class="text-caption text-medium-emphasis mb-1">Status</div>
      <v-select
        :model-value="bugsStore.currentBug.status"
        :items="statusOptions"
        :disabled="!canEditBugs"
        variant="outlined"
        density="compact"
        hide-details
        @update:model-value="onChangeStatus"
      />
    </div>

    <!-- Meta block -->
    <div class="d-flex flex-column ga-2 mb-4">
      <div v-if="bugsStore.currentBug.module" class="text-caption text-medium-emphasis">
        <strong>Module:</strong> {{ bugsStore.currentBug.module }}
      </div>

      <!-- Feature link -->
      <div class="text-caption text-medium-emphasis">
        <strong>Feature:</strong>
        <template v-if="bugsStore.currentBug.featureTitle">
          <v-chip
            size="small"
            variant="tonal"
            color="primary"
            class="ml-2"
            :closable="canEditBugs"
            @click:close="unlinkFeature"
          >
            {{ bugsStore.currentBug.featureTitle }}
          </v-chip>
        </template>
        <span v-else-if="!canEditBugs" class="ml-2">Unlinked</span>
        <v-autocomplete
          v-else
          v-model="linkedFeatureId"
          :items="featureOptions"
          :loading="featureSearchLoading"
          item-title="label"
          item-value="value"
          variant="outlined"
          density="compact"
          placeholder="Search features…"
          hide-details
          clearable
          class="ml-2 mt-1"
          style="max-width: 320px"
          @update:search="onFeatureSearch"
          @update:model-value="onLinkFeature"
        />
      </div>

      <!-- BUD link (read-only chip if present) -->
      <div v-if="bugsStore.currentBug.budNumber" class="text-caption text-medium-emphasis">
        <strong>BUD:</strong>
        <v-chip size="small" variant="tonal" color="primary" class="ml-2">
          BUD-{{ String(bugsStore.currentBug.budNumber).padStart(3, '0') }}
        </v-chip>
      </div>

      <!-- Assignee -->
      <div class="text-caption text-medium-emphasis">
        <strong>Assignee:</strong>
        <span v-if="!canAssignBugs" class="ml-2">
          {{ bugsStore.currentBug.assigneeName || 'Unassigned' }}
        </span>
        <v-autocomplete
          v-else
          v-model="assigneeId"
          :items="assigneeOptions"
          item-title="label"
          item-value="value"
          variant="outlined"
          density="compact"
          placeholder="Unassigned"
          hide-details
          clearable
          class="ml-2 mt-1"
          style="max-width: 320px"
          @update:model-value="onChangeAssignee"
        />
      </div>

      <div class="text-caption text-medium-emphasis">
        <strong>Reporter:</strong> {{ bugsStore.currentBug.reporterName || 'Unknown' }}
      </div>
      <div class="text-caption text-medium-emphasis">
        <strong>Reported:</strong> {{ formatDateTime(bugsStore.currentBug.createdAt) }}
      </div>
      <div v-if="bugsStore.currentBug.resolvedAt" class="text-caption text-medium-emphasis">
        <strong>Resolved:</strong> {{ formatDateTime(bugsStore.currentBug.resolvedAt) }}
      </div>
    </div>

    <v-divider class="mb-4" />

    <BugComments :bug-id="bugsStore.currentBug.id" />
  </v-card>
</template>

<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { useBugsStore } from '@/stores/bugs'
import { useFeaturesStore } from '@/stores/features'
import { useMembersStore } from '@/stores/members'
import { usePermissions } from '@/composables/usePermissions'
import { BUG_SEVERITY_COLORS, type BugStatusValue } from '@/types'
import { formatDateTime } from '@/utils/date'
import BugComments from './BugComments.vue'

defineEmits<{ (e: 'close'): void }>()

const bugsStore = useBugsStore()
const featuresStore = useFeaturesStore()
const membersStore = useMembersStore()
const { canEditBugs, canAssignBugs } = usePermissions()

const statusOptions: { title: string; value: BugStatusValue }[] = [
  { title: 'Open', value: 'open' },
  { title: 'In Progress', value: 'in-progress' },
  { title: 'Blocked', value: 'blocked' },
  { title: 'Resolved', value: 'resolved' },
  { title: 'Closed', value: 'closed' },
]

const editingTitle = ref(false)
const titleDraft = ref('')
const editingDescription = ref(false)
const descriptionDraft = ref('')
const linkedFeatureId = ref<string | null>(null)
const assigneeId = ref<string | null>(null)
const featureSearchQuery = ref('')
const featureSearchLoading = ref(false)
let featureSearchTimer: ReturnType<typeof setTimeout> | null = null

const featureOptions = computed(() =>
  featuresStore.items.map((f) => ({
    label: f.featureTitle,
    value: f.id,
  })),
)

const assigneeOptions = computed(() =>
  membersStore.members.map((m) => ({
    label: m.name || m.email,
    value: m.id,
  })),
)

watch(
  () => bugsStore.currentBug?.id,
  async (id) => {
    if (!id) return
    linkedFeatureId.value = bugsStore.currentBug?.featureId ?? null
    assigneeId.value = bugsStore.currentBug?.assigneeId ?? null
    if (canAssignBugs.value && membersStore.members.length === 0) {
      await membersStore.fetchMembers()
    }
  },
  { immediate: true },
)

function startEditTitle(): void {
  if (!bugsStore.currentBug) return
  titleDraft.value = bugsStore.currentBug.title
  editingTitle.value = true
}

function cancelTitle(): void {
  editingTitle.value = false
}

async function saveTitle(): Promise<void> {
  if (!bugsStore.currentBug || !titleDraft.value.trim()) return
  await bugsStore.updateBug(bugsStore.currentBug.id, { title: titleDraft.value.trim() })
  editingTitle.value = false
}

function startEditDescription(): void {
  if (!bugsStore.currentBug) return
  descriptionDraft.value = bugsStore.currentBug.description ?? ''
  editingDescription.value = true
}

function cancelDescription(): void {
  editingDescription.value = false
}

async function saveDescription(): Promise<void> {
  if (!bugsStore.currentBug) return
  await bugsStore.updateBug(bugsStore.currentBug.id, {
    description: descriptionDraft.value,
  })
  editingDescription.value = false
}

async function onChangeStatus(newStatus: BugStatusValue): Promise<void> {
  if (!bugsStore.currentBug) return
  await bugsStore.updateBug(bugsStore.currentBug.id, { status: newStatus })
}

async function onChangeAssignee(id: string | null): Promise<void> {
  if (!bugsStore.currentBug) return
  await bugsStore.updateBug(bugsStore.currentBug.id, { assigneeId: id })
}

async function onLinkFeature(id: string | null): Promise<void> {
  if (!bugsStore.currentBug || !id) return
  await bugsStore.updateBug(bugsStore.currentBug.id, { featureId: id })
}

async function unlinkFeature(): Promise<void> {
  if (!bugsStore.currentBug) return
  linkedFeatureId.value = null
  await bugsStore.updateBug(bugsStore.currentBug.id, { featureId: null })
}

function onFeatureSearch(query: string): void {
  featureSearchQuery.value = query
  if (featureSearchTimer) clearTimeout(featureSearchTimer)
  featureSearchTimer = setTimeout(async () => {
    featureSearchLoading.value = true
    await featuresStore.fetchPage({ q: query || undefined, mode: 'active' })
    featureSearchLoading.value = false
  }, 250)
}
</script>

<style scoped>
.cursor-pointer {
  cursor: pointer;
}
</style>
