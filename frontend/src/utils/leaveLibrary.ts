/**
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
 */

/** Pure helpers for the leave type library and the policy types that follow it. */
import type { Decimalish } from '@/types/leave'
import type { LibraryTypeRead, LibraryTypeUse, LibraryTypeWrite, LinkedTypeWrite } from '@/types/leaveLibrary'
import type { LeaveTypeRead, LeaveTypeWrite } from '@/types/leavePolicy'
import { pluralDays, toNumberOrNull } from '@/utils/leave'

/** Where a linked type's yearly quota comes from. */
export type QuotaChoice = 'library' | 'fixed' | 'unlimited'

/** "Sick  Leave" and "sick leave" name the same type (as the backend matches them). */
export function nameKey(name: string): string {
  return name.trim().split(/\s+/).join(' ').toLowerCase()
}

/** The quota picker's starting choice for a policy's linked type. */
export function quotaChoice(type: Pick<LeaveTypeRead, 'own_quota' | 'annual_quota_days'>): QuotaChoice {
  if (!type.own_quota) return 'library'
  return toNumberOrNull(type.annual_quota_days) === null ? 'unlimited' : 'fixed'
}

/** What to save for a choice; `days` only counts for an own fixed quota. */
export function linkBody(choice: QuotaChoice, days: number | null, isActive: boolean): LinkedTypeWrite {
  return {
    own_quota: choice !== 'library',
    annual_quota_days: choice === 'fixed' ? days : null,
    is_active: isActive,
  }
}

/** A quota to save is valid: whole or half days from 0 to 365, unless it's not the policy's own. */
export function validLinkQuota(choice: QuotaChoice, days: number | null): boolean {
  if (choice !== 'fixed') return true
  return typeof days === 'number' && days >= 0 && days <= 365 && Number.isInteger(days * 2)
}

/** "4 days", or "Unlimited". */
export function quotaLabel(days: Decimalish | null): string {
  const quota = toNumberOrNull(days)
  return quota === null ? 'Unlimited' : pluralDays(quota)
}

/** "Not on any policy yet", "On 1 policy", "On 3 policies". */
export function usesLabel(uses: readonly LibraryTypeUse[]): string {
  if (!uses.length) return 'Not on any policy yet'
  return `On ${uses.length} ${uses.length === 1 ? 'policy' : 'policies'}`
}

/** "UK – London · 6 days (own)", "India · 4 days", "UK · off". */
export function useLabel(use: LibraryTypeUse): string {
  if (!use.is_active) return `${use.policy_name} · off`
  const quota = quotaLabel(use.annual_quota_days)
  return `${use.policy_name} · ${use.own_quota ? `${quota} (own)` : quota}`
}

/** One library type as a policy's picker shows it. */
export interface LibraryChoice {
  entry: LibraryTypeRead
  /** Already on this policy: it can't be added twice. */
  onPolicy: boolean
  /** The policy's own type with the same code or name, which could follow the library instead. */
  ownMatch: LeaveTypeRead | null
}

export function libraryChoices(
  entries: readonly LibraryTypeRead[],
  policyTypes: readonly LeaveTypeRead[],
): LibraryChoice[] {
  const own = policyTypes.filter(t => t.template_id === null)
  return entries.map(entry => ({
    entry,
    onPolicy: policyTypes.some(t => t.template_id === entry.id),
    ownMatch: own.find(t => t.code === entry.code || nameKey(t.name) === nameKey(entry.name)) ?? null,
  }))
}

/** A library type as a leave type dialog draft. */
export function entryDraft(entry: LibraryTypeRead): LeaveTypeWrite {
  const { id: _id, uses: _uses, ...rules } = entry
  return { ...rules, is_active: true }
}

/** A dialog draft as a library type (on/off is per policy, not in the library). */
export function entryBody(draft: LeaveTypeWrite): LibraryTypeWrite {
  const { is_active: _active, ...rules } = draft
  return rules
}
