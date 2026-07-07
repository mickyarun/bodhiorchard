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
  Upload a self-contained wireframe HTML file as a per-repo design.

  Sits alongside the AI "Generate wireframe" flow: instead of streaming
  design HTML through an LLM tool call (which times out on large files),
  the browser POSTs the raw bytes straight to
  ``/buds/{budId}/designs/upload``. The chosen repo becomes the design's
  tab — a repo without a row yet appears as a new tab, an existing one is
  overwritten. Emits ``uploaded`` so the parent reloads the design list.
-->
<template>
  <div class="design-upload">
    <v-btn
      variant="text"
      size="small"
      prepend-icon="mdi-upload"
      :disabled="!editable"
      :title="!editable ? 'Move the BUD to Design to upload wireframes' : ''"
      @click="openDialog"
    >
      Upload HTML
    </v-btn>

    <v-dialog v-model="showDialog" max-width="480">
      <v-card color="surface" class="pa-6">
        <div class="text-h6 mb-1">Upload Design</div>
        <div class="text-body-2 text-medium-emphasis mb-4">
          Attach a self-contained HTML wireframe to a repository. It becomes
          that repo's design tab.
        </div>

        <v-select
          v-model="selectedRepoId"
          :items="repoItems"
          item-title="title"
          item-value="value"
          label="Repository"
          density="comfortable"
          variant="outlined"
          hide-details
          class="mb-3"
        />

        <v-file-input
          v-model="file"
          label="Wireframe HTML file"
          accept=".html,.htm"
          density="comfortable"
          variant="outlined"
          prepend-icon="mdi-file-code-outline"
          hide-details
          show-size
          class="mb-3"
        />

        <AppCallout
          v-if="errorMsg"
          variant="warning"
          :title="errorMsg"
          class="mb-2"
        />

        <v-card-actions class="pa-0 mt-4">
          <v-spacer />
          <v-btn variant="text" :disabled="uploading" @click="showDialog = false">
            Cancel
          </v-btn>
          <v-btn
            color="primary"
            variant="flat"
            :loading="uploading"
            :disabled="!selectedFile"
            @click="submit"
          >
            Upload
          </v-btn>
        </v-card-actions>
      </v-card>
    </v-dialog>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import type { AxiosError } from 'axios'
import { useBUDStore } from '@/stores/bud'
import { useSettingsStore } from '@/stores/settings'
import AppCallout from '@/components/common/AppCallout.vue'
import type { BUDDesign } from '@/types'

const props = withDefaults(
  defineProps<{
    budId: string
    editable?: boolean
  }>(),
  { editable: true },
)

const emit = defineEmits<{
  (e: 'uploaded', design: BUDDesign): void
}>()

const budStore = useBUDStore()
const settingsStore = useSettingsStore()

const showDialog = ref(false)
// v-file-input binds an array in Vuetify 3; we only ever take the first.
const file = ref<File[] | File | null>(null)
const selectedRepoId = ref<string | null>(null)
const uploading = ref(false)
const errorMsg = ref('')

// Any active repo is a valid upload target — unlike AI generation, an
// uploaded wireframe carries its own styling, so it doesn't depend on a
// repo having an extracted design system. ``null`` = a BUD-level design
// not scoped to any repo (the "Default" tab).
const repoItems = computed(() => [
  { title: 'No specific repo (default tab)', value: null as string | null },
  ...settingsStore.repos
    .filter(r => r.status === 'active')
    .map(r => ({ title: r.name, value: r.id as string | null })),
])

const selectedFile = computed<File | null>(() => {
  const f = file.value
  if (Array.isArray(f)) return f[0] ?? null
  return f
})

onMounted(() => {
  if (settingsStore.repos.length === 0) settingsStore.fetchRepos()
})

function openDialog(): void {
  errorMsg.value = ''
  file.value = null
  selectedRepoId.value = null
  showDialog.value = true
}

async function submit(): Promise<void> {
  const f = selectedFile.value
  if (!f) return
  uploading.value = true
  errorMsg.value = ''
  try {
    const created = await budStore.uploadDesign(props.budId, f, selectedRepoId.value)
    showDialog.value = false
    emit('uploaded', created)
  } catch (err) {
    const axiosErr = err as AxiosError<{ detail?: string }>
    errorMsg.value = axiosErr.response?.data?.detail || 'Upload failed. Please try again.'
  } finally {
    uploading.value = false
  }
}
</script>
