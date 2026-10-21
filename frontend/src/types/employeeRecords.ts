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

/**
 * Sensitive details, documents and the access log, mirroring
 * backend/app/schemas/employee_sensitive.py. Reads are always masked.
 */
import type { PersonRef } from '@/types/leave'

export type SensitiveField =
  | 'current_address'
  | 'permanent_address'
  | 'pan'
  | 'aadhaar'
  | 'passport_number'
  | 'bank_account_number'

export interface MaskedValue {
  is_set: boolean
  last4: string | null
}

export type SensitiveRead = Record<SensitiveField, MaskedValue> & {
  bank_name: string | null
  bank_ifsc: string | null
  updated_at: string | null
  can_edit: boolean
  can_reveal: boolean
}

/** Only the fields being changed; "" clears one. */
export type SensitiveWrite = Partial<Record<SensitiveField | 'bank_name' | 'bank_ifsc', string>>

export type DocumentType =
  | 'id_proof'
  | 'address_proof'
  | 'education'
  | 'employment'
  | 'offer_letter'
  | 'payslip'
  | 'other'

export interface DocumentRead {
  id: string
  doc_type: DocumentType
  filename: string
  mime_type: string
  size_bytes: number
  uploaded_by: PersonRef | null
  created_at: string
  /** HR can delete any document; others only the ones they uploaded. */
  can_delete: boolean
}

export interface DocumentList {
  documents: DocumentRead[]
  can_upload: boolean
  /** Largest file the server accepts. */
  max_upload_bytes: number
}

export type AccessAction =
  | 'field_revealed'
  | 'details_updated'
  | 'document_uploaded'
  | 'document_viewed'
  | 'document_deleted'

export interface AccessLogEntry {
  action: AccessAction
  actor: PersonRef
  target: string
  at: string
}
