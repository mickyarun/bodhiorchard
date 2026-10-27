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
     The employee and HR can upload. HR deletes any document; anyone else
     only what they uploaded, so a wrong file or type can be sent again. -->
<template>
  <AppPanel title="Documents" flush>
    <template v-if="list?.can_upload" #action>
      <v-btn variant="outlined" size="small" prepend-icon="mdi-upload" @click="uploading = true">Upload</v-btn>
    </template>
    <div class="docs__body">
      <p class="docs__note">
        PDF, JPEG or PNG<template v-if="list">, up to {{ formatBytes(list.max_upload_bytes) }}</template>. Stored
        encrypted, and every open is logged.
        <template v-if="list?.documents.some(d => d.can_delete)">Wrong file or type? Delete it and upload again.</template>
      </p>
      <v-progress-linear v-if="docs.loading.value" indeterminate color="primary" />
      <AppCallout v-if="docs.error.value || actionError" variant="error">
        {{ actionError || docs.error.value }}
      </AppCallout>
      <p v-if="list && !list.documents.length" class="docs__empty">No documents yet.</p>
    </div>
    <div v-if="list?.documents.length" class="docs__scroll">
      <table class="docs__table">
        <thead>
          <tr>
            <th scope="col">Document</th>
            <th scope="col">Type</th>
            <th scope="col" class="docs__optional">Size</th>
            <th scope="col" class="docs__optional">Added</th>
            <th scope="col"><span class="d-sr-only">Actions</span></th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="doc in list.documents" :key="doc.id">
            <td class="docs__filename">{{ doc.filename }}</td>
            <td>{{ DOC_TYPE_LABELS[doc.doc_type] }}</td>
            <td class="docs__optional">{{ formatBytes(doc.size_bytes) }}</td>
            <td class="docs__optional">{{ formatTimestampDay(doc.created_at) }} · {{ doc.uploaded_by?.name ?? '—' }}</td>
            <td class="docs__actions">
              <v-btn size="small" variant="text" :aria-label="`Open ${doc.filename}`" @click="openDoc(doc, false)">Open</v-btn>
              <v-btn size="small" variant="text" :aria-label="`Download ${doc.filename}`" @click="openDoc(doc, true)">
                Download
              </v-btn>
              <v-btn
                v-if="doc.can_delete"
                size="small"
                variant="text"
                color="error"
                :aria-label="`Delete ${doc.filename}`"
                @click="deleting = doc"
              >
                Delete
              </v-btn>
            </td>
          </tr>
        </tbody>
      </table>
    </div>
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
  </AppPanel>
</template>

<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import AppCallout from '@/components/common/AppCallout.vue'
import AppPanel from '@/components/common/AppPanel.vue'
import DocumentUploadDialog from '@/components/people/DocumentUploadDialog.vue'
import ConfirmDialog from '@/components/settings/code/ConfirmDialog.vue'
import { useEmployeeDocuments } from '@/composables/useEmployeeDocuments'
import type { DocumentRead } from '@/types/employeeRecords'
import { formatTimestampDay } from '@/utils/employee'
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
.docs__body {
  display: flex;
  flex-direction: column;
  gap: 12px;
  padding: 0 20px 16px;
}
.docs__note,
.docs__empty {
  margin: 0;
  font-size: 13px;
  color: rgb(var(--v-theme-on-surface-variant));
}
.docs__empty {
  font-size: 14px;
}
.docs__scroll {
  overflow-x: auto;
}
.docs__table {
  width: 100%;
  border-collapse: collapse;
  font-size: 14px;
}
.docs__table th {
  text-align: left;
  padding: 10px 12px;
  font-size: 12px;
  font-weight: 600;
  color: rgb(var(--v-theme-on-surface-variant));
  background: rgb(var(--v-theme-surface-variant));
}
.docs__table td {
  padding: 8px 12px;
  border-top: 1px solid var(--color-rule-2);
}
.docs__table th:first-child,
.docs__table td:first-child {
  padding-left: 20px;
}
.docs__filename {
  max-width: 280px;
  overflow-wrap: anywhere;
}
.docs__actions {
  text-align: right;
  white-space: nowrap;
}
@media (max-width: 600px) {
  .docs__optional {
    display: none;
  }
  .docs__body {
    padding: 0 16px 16px;
  }
  .docs__actions {
    white-space: normal;
  }
}
</style>
