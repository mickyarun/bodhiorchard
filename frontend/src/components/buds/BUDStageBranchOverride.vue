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
  Inline tracking-branch override for a single release stage (UAT / Prod).

  Default is the repo-wide branch ("main", "release/uat") shown read-only
  with an "Edit" affordance. When the user sets a per-BUD override
  (e.g. "release/*" so a release-train BUD picks up release/2026-08-01),
  it persists onto ``bud_documents.branch_overrides[stage]`` via PATCH
  and the parent re-fetches the stage panel so the new pattern feeds
  the open-PR filter immediately.

  Patterns are fnmatch-style; the same matcher (``branch_matches``)
  drives release-detection on the backend, so wildcards behave the way
  the rest of the platform expects.
-->

<template>
  <v-card variant="outlined" class="pa-3 mb-4">
    <div class="d-flex align-center ga-2 flex-wrap">
      <v-icon icon="mdi-source-branch" size="18" />
      <span class="text-body-2 text-medium-emphasis">Tracking branch:</span>
      <code class="bud-stage-branch__pattern">{{ displayPattern || 'not set' }}</code>
      <v-chip v-if="override" size="x-small" variant="tonal" color="primary">
        BUD override
      </v-chip>
      <v-spacer />
      <v-btn
        size="small"
        variant="text"
        prepend-icon="mdi-pencil-outline"
        @click="open = true"
      >
        Edit
      </v-btn>
    </div>
    <div class="text-caption text-medium-emphasis mt-1">
      Open PRs are matched against this pattern on each impacted repo.
      Supports fnmatch wildcards — e.g. <code>release/*</code> matches
      <code>release/2026-08-01</code>.
    </div>
  </v-card>

  <v-dialog v-model="open" max-width="520" persistent>
    <v-card>
      <v-card-title class="d-flex align-center ga-2">
        <v-icon icon="mdi-source-branch" />
        Tracking branch for {{ stageLabel }}
      </v-card-title>
      <v-card-text>
        <p class="text-body-2 text-medium-emphasis mb-3">
          Override the branch this BUD watches for {{ stageLabel }} PRs.
          Leave blank to fall back to the repo-wide
          <code>{{ stage === 'uat' ? 'uat_branch' : 'main_branch' }}</code>
          setting.
        </p>
        <p
          v-if="impactedRepoCount > 1"
          class="text-caption text-medium-emphasis mb-3"
        >
          The pattern applies to all {{ impactedRepoCount }} impacted repos.
          If your repos disagree on the {{ stageLabel }} branch shape, use a
          wildcard like <code>release/*</code> that matches both.
        </p>
        <v-text-field
          v-model.trim="draft"
          label="Branch pattern"
          placeholder="e.g. release/* or main"
          variant="outlined"
          density="compact"
          autofocus
          :disabled="saving"
          :error-messages="error ? [error] : []"
          @keyup.enter="save"
        />
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
        <v-btn
          v-if="override"
          variant="text"
          color="error"
          prepend-icon="mdi-close-circle-outline"
          :disabled="saving"
          @click="clear"
        >
          Clear override
        </v-btn>
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
import type { ReleaseStage } from '@/types'

const props = defineProps<{
  budId: string
  stage: ReleaseStage
  /** The per-BUD pattern when set, ``null`` to fall back to the repo default. */
  override: string | null
  /** Repo-wide default for this stage — the value used when no override exists.
   *  Already pre-resolved by the parent (whichever impacted repo it picks). */
  defaultBranch: string | null
  /** Number of impacted repos this BUD touches. Drives the
   *  "applies to N repos" disclosure so the user understands the
   *  per-stage (not per-repo) granularity before committing a pattern. */
  impactedRepoCount?: number
}>()

const emit = defineEmits<{
  (e: 'saved'): void
}>()

const open = ref(false)
const draft = ref('')
const saving = ref(false)
const error = ref<string | null>(null)

watch(open, (isOpen) => {
  if (isOpen) {
    draft.value = props.override ?? ''
    error.value = null
  }
})

const displayPattern = computed(() => props.override ?? props.defaultBranch ?? '')

const impactedRepoCount = computed(() => props.impactedRepoCount ?? 0)

const stageLabel = computed(() => (props.stage === 'uat' ? 'UAT' : 'Production'))

function cancel(): void {
  if (saving.value) return
  open.value = false
}

async function patch(branchOverrides: Record<string, string | null>): Promise<void> {
  await api.patch(`/v1/buds/${props.budId}`, {
    branch_overrides: branchOverrides,
  })
  emit('saved')
  open.value = false
}

async function save(): Promise<void> {
  saving.value = true
  error.value = null
  try {
    const value = draft.value.trim()
    if (!value) {
      // Empty input via Save = clear the override (equivalent to the
      // Clear button). Friendlier than forcing the user to pick a button.
      await patch({ [props.stage]: null })
      return
    }
    await patch({ [props.stage]: value })
  } catch (e: unknown) {
    const msg = (e as { response?: { data?: { detail?: string } } })
      ?.response?.data?.detail
    error.value = msg ?? 'Failed to save override. Please retry.'
  } finally {
    saving.value = false
  }
}

async function clear(): Promise<void> {
  saving.value = true
  error.value = null
  try {
    await patch({ [props.stage]: null })
  } catch (e: unknown) {
    const msg = (e as { response?: { data?: { detail?: string } } })
      ?.response?.data?.detail
    error.value = msg ?? 'Failed to clear override. Please retry.'
  } finally {
    saving.value = false
  }
}
</script>

<style scoped>
.bud-stage-branch__pattern {
  font-family: 'JetBrains Mono', 'Fira Code', ui-monospace, SFMono-Regular, monospace;
  font-size: 0.85em;
  padding: 2px 8px;
  border-radius: 4px;
  background: rgba(var(--v-theme-on-surface), 0.06);
}
</style>
