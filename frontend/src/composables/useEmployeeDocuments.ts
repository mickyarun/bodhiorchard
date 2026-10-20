// Copyright 2025-2026 Arun Rajkumar
//
// Licensed under the Apache License, Version 2.0 (the "License");
// you may not use this file except in compliance with the License.
// You may obtain a copy of the License at
//
//     http://www.apache.org/licenses/LICENSE-2.0
//
// Unless required by applicable law or agreed to in writing, software
// distributed under the License is distributed on an "AS IS" BASIS,
// WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
// See the License for the specific language governing permissions and
// limitations under the License.

/** One person's documents: list, upload, open, download, delete. */
import { ref } from 'vue'

import api from '@/services/api'
import type { DocumentList, DocumentRead, DocumentType } from '@/types/employeeRecords'
import { extractApiError, extractBlobApiError } from '@/utils/errors'

export function useEmployeeDocuments(userId: () => string) {
  const data = ref<DocumentList | null>(null)
  const loading = ref(false)
  const error = ref('')

  async function load(): Promise<void> {
    loading.value = true
    error.value = ''
    try {
      data.value = (await api.get<DocumentList>(`/v1/employees/${userId()}/documents`)).data
    } catch (err) {
      error.value = extractApiError(err, "Couldn't load documents.")
    } finally {
      loading.value = false
    }
  }

  async function upload(docType: DocumentType, file: File): Promise<string | null> {
    const form = new FormData()
    form.append('doc_type', docType)
    form.append('file', file)
    try {
      await api.post(`/v1/employees/${userId()}/documents`, form)
      await load()
      return null
    } catch (err) {
      return extractApiError(err, "Couldn't upload this file. Try again.")
    }
  }

  /** Fetch the decrypted file and open it in a new tab, or save it. */
  async function open(doc: DocumentRead, download: boolean): Promise<string | null> {
    try {
      const response = await api.get<Blob>(`/v1/employees/documents/${doc.id}/content`, {
        params: { download },
        responseType: 'blob',
      })
      const url = URL.createObjectURL(response.data)
      if (download) {
        const link = document.createElement('a')
        link.href = url
        link.download = doc.filename
        link.click()
      } else {
        window.open(url, '_blank', 'noopener')
      }
      // Give the new tab time to load before releasing the decrypted copy.
      setTimeout(() => URL.revokeObjectURL(url), 60_000)
      return null
    } catch (err) {
      // The body is a Blob here, even for errors: read the server's reason.
      return await extractBlobApiError(err, "Couldn't open this document.")
    }
  }

  async function remove(doc: DocumentRead): Promise<string | null> {
    try {
      await api.delete(`/v1/employees/documents/${doc.id}`)
      await load()
      return null
    } catch (err) {
      return extractApiError(err, "Couldn't delete this document.")
    }
  }

  return { data, loading, error, load, upload, open, remove }
}
