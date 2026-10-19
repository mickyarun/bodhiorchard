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

/** Labels and masking for sensitive details, documents and the access log (pure). */
import type {
  AccessAction,
  AccessLogEntry,
  DocumentType,
  MaskedValue,
  SensitiveField,
} from '@/types/employeeRecords'

export const FIELD_LABELS: Record<SensitiveField, string> = {
  current_address: 'Current address',
  permanent_address: 'Permanent address',
  pan: 'PAN',
  aadhaar: 'Aadhaar',
  passport_number: 'Passport number',
  bank_account_number: 'Account number',
}

export const DOC_TYPE_LABELS: Record<DocumentType, string> = {
  id_proof: 'ID proof',
  address_proof: 'Address proof',
  education: 'Education',
  employment: 'Previous employment',
  offer_letter: 'Offer letter',
  payslip: 'Payslip',
  other: 'Other',
}

const ACTION_LABELS: Record<AccessAction, string> = {
  field_revealed: 'viewed',
  details_updated: 'changed',
  document_uploaded: 'uploaded a document',
  document_viewed: 'opened a document',
  document_deleted: 'deleted a document',
}

/** "•••• 7890" for an ID, "Saved" for an address, "—" when empty. */
export function maskLabel(value: MaskedValue): string {
  if (!value.is_set) return '—'
  return value.last4 ? `•••• ${value.last4}` : 'Saved'
}

/** "Priya viewed Account number", "Ravi changed PAN and Aadhaar". */
export function accessLine(entry: AccessLogEntry): string {
  const verb = ACTION_LABELS[entry.action]
  if (entry.action !== 'field_revealed' && entry.action !== 'details_updated') {
    return `${entry.actor.name} ${verb}`
  }
  const labels = entry.target
    .split(',')
    .map(field => FIELD_LABELS[field as SensitiveField] ?? field.replace(/_/g, ' '))
  const listed = labels.length > 1 ? `${labels.slice(0, -1).join(', ')} and ${labels.at(-1)}` : labels[0]
  return `${entry.actor.name} ${verb} ${listed}`
}

/** "1.2 MB", "340 KB". */
export function formatBytes(bytes: number): string {
  if (bytes >= 1024 * 1024) return `${(bytes / (1024 * 1024)).toFixed(1)} MB`
  return `${Math.max(1, Math.round(bytes / 1024))} KB`
}

/** Seconds a revealed value stays on screen. */
export const REVEAL_SECONDS = 30
