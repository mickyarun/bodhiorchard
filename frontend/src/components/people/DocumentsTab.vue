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

<!-- Documents: encrypted at rest, opened in memory, every open logged.
     The employee and HR can upload; only HR deletes. -->
<template>
  <section>
    <div class="d-flex align-center justify-space-between flex-wrap ga-3 mb-4">
      <p class="text-body-2 text-medium-emphasis">PDF, JPEG or PNG, up to 10 MB. Stored encrypted.</p>
      <v-btn v-if="list?.can_upload" color="primary" variant="tonal" size="small" prepend-icon="mdi-upload" @click="uploading = true">
        Upload
      </v-btn>
    </div>
    <v-progress-linear v-if="docs.loading.value" indeterminate color="primary" class="mb-4" />
    <AppCallout v-if="docs.error.value || actionError" variant="error" class="mb-4">
      {{ actionError || docs.error.value }}
    </AppCallout>
    <p v-if="list && !list.documents.length" class="text-body-2 text-medium-emphasis">No documents yet.</p>
    <v-table v-else-if="list" density="comfortable">
      <thead>
        <tr><th>Document</th><th>Type</th><th>Size</th><th>Added</th><th /></tr>
      </thead>
      <tbody>
        <tr v-for="doc in list.documents" :key="doc.id">
          <td class="filename">{{ doc.filename }}</td>
          <td>{{ DOC_TYPE_LABELS[doc.doc_type] }}</td>
          <td>{{ formatBytes(doc.size_bytes) }}</td>
          <td>{{ formatDateOnly(doc.created_at.slice(0, 10)) }} · {{ doc.uploaded_by?.name ?? '—' }}</td>
          <td class="text-right text-no-wrap">
            <v-btn size="small" variant="text" @click="openDoc(doc, false)">Open</v-btn>
            <v-btn size="small" variant="text" @click="openDoc(doc, true)">Download</v-btn>
            <v-btn v-if="list.can_delete" size="small" variant="text" color="error" @click="deleting = doc">Delete</v-btn>
          </td>
        </tr>
      </tbody>
    </v-table>
    <DocumentUploadDialog v-model="uploading" :upload="docs.upload" :max-bytes="list?.max_upload_bytes ?? null" />
    <ConfirmDialog
      :model-value="!!deleting"
      title="Delete this document?"
      :message="`${deleting?.filename ?? ''} will be removed for good.`"
      confirm-label="Delete"
      icon="mdi-delete-outline"
      @update:model-value="value => !value && (deleting = null)"
      @confirm="remove"
    />
  </section>
</template>

<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import AppCallout from '@/components/common/AppCallout.vue'
import DocumentUploadDialog from '@/components/people/DocumentUploadDialog.vue'
import ConfirmDialog from '@/components/settings/code/ConfirmDialog.vue'
import { useEmployeeDocuments } from '@/composables/useEmployeeDocuments'
import type { DocumentRead } from '@/types/employeeRecords'
import { formatDateOnly } from '@/utils/employee'
import { DOC_TYPE_LABELS, formatBytes } from '@/utils/employeeRecords'

const props = defineProps<{ userId: string }>()
const docs = useEmployeeDocuments(() => props.userId)
const list = computed(() => docs.data.value)
const uploading = ref(false)
const deleting = ref<DocumentRead | null>(null)
const actionError = ref('')

async function openDoc(doc: DocumentRead, download: boolean): Promise<void> {
  actionError.value = (await docs.open(doc, download)) ?? ''
}

async function remove(): Promise<void> {
  const doc = deleting.value
  deleting.value = null
  if (doc) actionError.value = (await docs.remove(doc)) ?? ''
}

watch(() => props.userId, () => void docs.load(), { immediate: true })
</script>

<style scoped>
.filename {
  max-width: 280px;
  overflow-wrap: anywhere;
}
</style>
