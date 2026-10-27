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
  <!-- Closes route through `dismiss` rather than straight to the parent:
    after a part-failed create the bug exists, and letting ESC or a scrim
    click through would drop the `created` event (board never refreshes)
    and leave this component's `createdBug` state set, wedging the next
    "Report a Bug" into a retry against the previous bug. -->
  <v-dialog
    :model-value="modelValue"
    max-width="540"
    @update:model-value="onDialogToggle"
  >
    <v-card color="surface" class="pa-6">
      <h2 class="bug-create__title">Report a bug</h2>

      <!-- Reached only when the bug was filed but an attachment upload
        failed. The bug exists, so the primary action switches from
        "file it" to "retry the leftovers" — pressing it again must not
        create a duplicate. -->
      <AppCallout v-if="createdBug" variant="warning" class="mb-4">
        BUG-{{ String(createdBug.bugNumber).padStart(3, '0') }} was filed, but
        {{ stagedFiles.length }} attachment{{ stagedFiles.length === 1 ? '' : 's' }}
        didn't upload. Retry below, or close and add them from the bug.
      </AppCallout>

      <BugReportFields
        v-model:title="title"
        v-model:description="description"
        v-model:severity="severity"
        v-model:module="module"
        :disabled="!!createdBug"
      />

      <!-- BUD link path: only shown when the dialog is opened from a
        BUD context (BUDBugsPanel passes ``budId``). The parent BUD
        view already shows the formatted ``BUD-NNN`` number, so we
        just acknowledge the link inline. -->
      <div v-if="budId" class="text-caption text-medium-emphasis mb-3">
        This bug will be linked to the current BUD.
      </div>

      <!-- Feature picker — production-bug surface only. -->
      <template v-else-if="resolvedBugType === 'production'">
        <BugFeaturePicker
          v-model="selectedFeatureId"
          label="Feature (optional)"
          hint="Left empty, Glideship links the closest feature itself."
          class="mb-3"
        />
      </template>

      <v-divider class="my-4" />

      <!-- Staged until the bug exists: the upload endpoint is keyed on a
        bug id, so files picked here are held in memory and posted right
        after createBug() returns. -->
      <BugAttachments ref="attachmentsRef" v-model="stagedFiles" :bug-id="null" />

      <v-card-actions class="pa-0 mt-4">
        <v-spacer />
        <v-btn variant="text" @click="dismiss">{{ createdBug ? 'Close' : 'Cancel' }}</v-btn>
        <v-btn
          color="primary"
          variant="flat"
          :disabled="!title?.trim()"
          :loading="saving"
          @click="submit"
        >
          {{ createdBug ? 'Retry upload' : 'Report bug' }}
        </v-btn>
      </v-card-actions>
    </v-card>
  </v-dialog>
</template>

<script setup lang="ts">
import { computed, ref } from 'vue'
import AppCallout from '@/components/common/AppCallout.vue'
import BugAttachments from '@/components/bugs/BugAttachments.vue'
import BugFeaturePicker from '@/components/bugs/BugFeaturePicker.vue'
import BugReportFields from '@/components/bugs/BugReportFields.vue'
import { useBugsStore } from '@/stores/bugs'
import type { BugRead, BugSeverity } from '@/types'

const props = defineProps<{
  modelValue: boolean
  budId?: string | null
  defaultBugType?: 'testing' | 'production'
}>()

const emit = defineEmits<{
  (e: 'update:modelValue', value: boolean): void
  (e: 'created', bug: BugRead): void
}>()

const bugsStore = useBugsStore()

const title = ref('')
const description = ref('')
const severity = ref<BugSeverity>('medium')
const module = ref('')
const selectedFeatureId = ref<string | null>(null)
const stagedFiles = ref<File[]>([])
const attachmentsRef = ref<InstanceType<typeof BugAttachments> | null>(null)
// Set only when the bug was created but some attachment failed to
// upload. Its presence is what stops a second press from filing a
// duplicate, and what flips the dialog into "retry" mode.
const createdBug = ref<BugRead | null>(null)
const saving = ref(false)

// When opened from a BUD detail panel the bug is by definition a
// testing bug; otherwise inherit the board's current scope (production
// is the /bugs page default).
const resolvedBugType = computed(() => {
  if (props.budId) return 'testing'
  return props.defaultBugType ?? 'production'
})

async function submit(): Promise<void> {
  // Retry path: the bug already exists, so only the leftover files go.
  if (createdBug.value) {
    saving.value = true
    const done = (await attachmentsRef.value?.flush(createdBug.value.id)) ?? true
    saving.value = false
    if (done) finish(createdBug.value)
    return
  }

  if (!title.value.trim()) return
  saving.value = true
  const bug = await bugsStore.createBug({
    title: title.value.trim(),
    description: description.value.trim() || undefined,
    severity: severity.value,
    module: module.value.trim() || undefined,
    budId: props.budId || undefined,
    featureId: !props.budId ? selectedFeatureId.value || undefined : undefined,
    bugType: !props.budId ? resolvedBugType.value : undefined,
  })
  if (!bug) {
    saving.value = false
    return
  }

  // Attachments post after creation because the endpoint is keyed on
  // the new bug's id. If any fail we keep the dialog open rather than
  // closing over the error — a reporter who watched a screenshot
  // silently not attach is worse off than one asked to retry.
  const allStored = (await attachmentsRef.value?.flush(bug.id)) ?? true
  saving.value = false
  if (!allStored) {
    createdBug.value = bug
    return
  }
  finish(bug)
}

/** Route every close — button, ESC, scrim — through `dismiss`. */
function onDialogToggle(open: boolean): void {
  if (open) emit('update:modelValue', true)
  else dismiss()
}

/** Close without filing, or close out a part-failed create. */
function dismiss(): void {
  if (createdBug.value) {
    finish(createdBug.value)
    return
  }
  // Drop anything staged. The dialog stays mounted, so files abandoned
  // on a cancel would otherwise reappear attached to the next bug the
  // user starts reporting.
  stagedFiles.value = []
  emit('update:modelValue', false)
}

/** Reset the form, close, and tell the parent about the new bug. */
function finish(bug: BugRead): void {
  title.value = ''
  description.value = ''
  severity.value = 'medium'
  module.value = ''
  selectedFeatureId.value = null
  stagedFiles.value = []
  createdBug.value = null
  emit('update:modelValue', false)
  emit('created', bug)
}
</script>

<style scoped>
.bug-create__title {
  margin: 0 0 16px;
  font-size: var(--text-md);
  font-weight: 600;
}
</style>
