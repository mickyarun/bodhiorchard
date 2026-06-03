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

<!--
  Edit the impacted_repos array on a BUD. The tech-arch agent's
  initial guess is often close but not perfect; this dialog lets the
  user correct or extend the set without having to re-run the agent.

  Persistence is a single PATCH /v1/buds/{id} with the full new list
  (the column has no merge key, so partial edits don't make sense).
  Removing a repo only hides its PRs from the release-stage tabs —
  the PR rows themselves keep their bud_id so the backend log
  ``bud_impacted_repos_edited_post_planning`` captures the audit trail.
-->

<template>
  <v-dialog
    v-model="open"
    max-width="560"
    :persistent="saving"
  >
    <v-card>
      <v-card-title class="d-flex align-center ga-2">
        <v-icon icon="mdi-source-repository-multiple" />
        Impacted repositories
      </v-card-title>
      <v-card-text>
        <p class="text-body-2 text-medium-emphasis mb-3">
          Pick every repo this BUD touches. The release-stage tabs filter
          their open-PR list by this set, and the code-review status feed
          watches these repos for merges.
        </p>
        <v-progress-linear
          v-if="trackedReposLoading"
          indeterminate
          color="primary"
          class="mb-3"
        />
        <v-text-field
          v-model.trim="filter"
          density="compact"
          variant="outlined"
          prepend-inner-icon="mdi-magnify"
          placeholder="Filter by name or path"
          hide-details
          class="mb-3"
          :disabled="saving"
        />
        <div
          v-if="!visibleRepos.length && !retiredRows.length && !trackedReposLoading"
          class="text-caption text-medium-emphasis text-center py-6"
        >
          <template v-if="filter">
            No tracked repos match "<code>{{ filter }}</code>".
          </template>
          <template v-else>
            No tracked repos yet. Add a repo in Settings first.
          </template>
        </div>
        <div v-else class="bud-impacted-repos__list">
          <v-checkbox
            v-for="repo in visibleRepos"
            :key="repo.id"
            v-model="selectedIds"
            :value="repo.id"
            density="compact"
            hide-details
            :disabled="saving"
          >
            <template #label>
              <div class="d-flex align-center ga-2 flex-grow-1 min-w-0">
                <v-icon icon="mdi-source-repository" size="16" />
                <span class="text-body-2 flex-shrink-0">{{ repo.name }}</span>
                <span class="text-caption text-medium-emphasis text-truncate">{{ repo.path }}</span>
              </div>
            </template>
          </v-checkbox>

          <!-- Retired-but-still-on-the-BUD rows: keep them checkable so
               the user can preserve the legacy assignment, but mark them
               clearly so accidentally re-saving with the checkbox off
               (an effective remove) is a conscious choice. -->
          <v-checkbox
            v-for="retired in retiredRows"
            :key="`retired:${retired.id}`"
            v-model="selectedIds"
            :value="retired.id"
            density="compact"
            hide-details
            :disabled="saving"
          >
            <template #label>
              <div class="d-flex align-center ga-2 flex-grow-1 min-w-0">
                <v-icon icon="mdi-source-repository" size="16" color="warning" />
                <span class="text-body-2 flex-shrink-0">{{ retired.name }}</span>
                <v-chip size="x-small" variant="tonal" color="warning">retired</v-chip>
              </div>
            </template>
          </v-checkbox>
        </div>
        <p v-if="error" class="text-caption text-error mt-2">{{ error }}</p>
      </v-card-text>
      <v-card-actions class="px-4 pb-4">
        <v-btn
          variant="text"
          :disabled="saving"
          @click="cancel"
        >
          Cancel
        </v-btn>
        <v-spacer />
        <span
          class="text-caption text-medium-emphasis mr-3"
          aria-live="polite"
        >
          {{ selectedIds.length }} selected
        </span>
        <v-btn
          color="primary"
          variant="flat"
          :loading="saving"
          @click="save"
        >
          Save
        </v-btn>
      </v-card-actions>
    </v-card>
  </v-dialog>
</template>

<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import api from '@/services/api'
import { useSettingsStore } from '@/stores/settings'

interface ImpactedRepo {
  repo_id?: string
  repo_name: string
}

const props = defineProps<{
  modelValue: boolean
  budId: string
  /** Current impacted_repos array — the dialog initialises selection
   *  from this on open and PATCHes the replacement on save. */
  current: ImpactedRepo[] | null
}>()

const emit = defineEmits<{
  (e: 'update:modelValue', value: boolean): void
  /** Fired after a successful PATCH. Parent should re-fetch the BUD. */
  (e: 'saved'): void
}>()

const settingsStore = useSettingsStore()
const trackedReposLoading = ref(false)
const filter = ref('')
const selectedIds = ref<string[]>([])
const saving = ref(false)
const error = ref<string | null>(null)

// In-flight ``fetchRepos`` promise. Subsequent opens reuse the same
// promise instead of spawning a second GET, so reopen-during-load is
// safe and ``trackedReposLoading`` stays accurate.
let inFlightFetch: Promise<void> | null = null

// Rows that ARE on the BUD but are no longer ``active`` in the tracked
// repo list. Rendered separately with a "retired" chip so the user can
// either keep the legacy assignment by leaving them checked, or
// consciously drop them by unchecking — neither path is silent.
interface RetiredRow { id: string; name: string }
const retiredRows = ref<RetiredRow[]>([])

const open = computed({
  get: () => props.modelValue,
  set: (v: boolean) => emit('update:modelValue', v),
})

// Only ``active`` tracked repos can be chosen. ``ignored`` / ``removed``
// rows are excluded so the user cannot accidentally re-introduce a repo
// the workspace admin has retired.
const activeRepos = computed(() =>
  settingsStore.repos.filter((r) => r.status === 'active'),
)

const visibleRepos = computed(() => {
  const term = filter.value.toLowerCase()
  if (!term) return activeRepos.value
  return activeRepos.value.filter(
    (r) =>
      r.name.toLowerCase().includes(term)
      || (r.path?.toLowerCase().includes(term) ?? false),
  )
})

async function refreshRepos(): Promise<void> {
  // Always refresh on open so a repo added in another tab shows up in
  // the picker before driving a destructive PATCH. Re-uses the in-flight
  // promise if another open is mid-fetch.
  if (inFlightFetch) {
    await inFlightFetch
    return
  }
  trackedReposLoading.value = true
  inFlightFetch = settingsStore.fetchRepos()
  try {
    await inFlightFetch
  } finally {
    trackedReposLoading.value = false
    inFlightFetch = null
  }
}

watch(open, async (isOpen) => {
  if (!isOpen) return
  error.value = null
  filter.value = ''
  await refreshRepos()

  // Partition the BUD's current rows against the freshly-loaded active
  // repo set: matches go into the selection (auto-checked), misses
  // surface as retired-but-still-on-the-BUD rows so the user can keep
  // them checked or consciously drop them.
  const activeIds = new Set(activeRepos.value.map((r) => r.id))
  const seedSelected: string[] = []
  const seedRetired: RetiredRow[] = []
  for (const r of props.current ?? []) {
    if (typeof r.repo_id !== 'string') continue
    if (activeIds.has(r.repo_id)) {
      seedSelected.push(r.repo_id)
    } else {
      seedRetired.push({ id: r.repo_id, name: r.repo_name })
    }
  }
  selectedIds.value = [...seedSelected, ...seedRetired.map((r) => r.id)]
  retiredRows.value = seedRetired
})

function cancel(): void {
  if (saving.value) return
  open.value = false
}

async function save(): Promise<void> {
  // Conscious-clear gate: dropping every repo from a BUD that previously
  // had some hides its PRs from the release-stage tabs and removes the
  // signal that smart-assignment + code-review status depend on. Surface
  // the consequence before letting the user save the empty list.
  const previouslyHadRepos = (props.current ?? []).length > 0
  if (selectedIds.value.length === 0 && previouslyHadRepos) {
    const ok = window.confirm(
      'Clear all impacted repositories?\n\n'
        + 'The release-stage tabs will no longer surface open PRs for this BUD, '
        + 'and code-review status will go quiet until at least one repo is added back.',
    )
    if (!ok) return
  }

  saving.value = true
  error.value = null
  try {
    // Send the full new list, not a diff — the column has no per-row
    // merge identity. Retired rows the user kept checked are preserved
    // with their original repo_name (the active repos list does not
    // know them) so closing then reopening the dialog shows the same
    // state. The PATCH validator accepts the exact JSONB shape the
    // tech-arch agent originally wrote.
    const retiredById = new Map(retiredRows.value.map((r) => [r.id, r]))
    const next: ImpactedRepo[] = selectedIds.value.map((id) => {
      const retired = retiredById.get(id)
      if (retired) return { repo_id: id, repo_name: retired.name }
      const repo = activeRepos.value.find((r) => r.id === id)
      return { repo_id: id, repo_name: repo?.name ?? '' }
    })
    await api.patch(`/v1/buds/${props.budId}`, { impacted_repos: next })
    emit('saved')
    open.value = false
  } catch (e: unknown) {
    const msg = (e as { response?: { data?: { detail?: string } } })
      ?.response?.data?.detail
    error.value = msg ?? 'Failed to update impacted repos. Please retry.'
  } finally {
    saving.value = false
  }
}
</script>

<style scoped>
.bud-impacted-repos__list {
  max-height: 280px;
  overflow-y: auto;
  border: 1px solid rgba(var(--v-theme-on-surface), 0.08);
  border-radius: 8px;
  padding: 4px 8px;
}
.min-w-0 {
  min-width: 0;
}
</style>
