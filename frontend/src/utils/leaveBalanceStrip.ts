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

/** Text for the request dialog's balance strip (pure, so it's testable). */
import type { Balance } from '@/types/leave'
import { formatDays, pluralDays, toNumber } from '@/utils/leave'

/** "Casual: 2 used · 1 pending": what's left is in the type picker already. */
export function balanceChipLabel(balance: Balance): string {
  const used = `${balance.leave_type.name}: ${formatDays(toNumber(balance.used))} used`
  const pending = toNumber(balance.pending)
  return pending ? `${used} · ${formatDays(pending)} pending` : used
}

/** The WFH allowance line, or '' when the policy has no allowance. */
export function wfhAllowanceLine(left: number | null): string {
  if (left === null) return ''
  return left > 0
    ? `${pluralDays(left)} of work from home left this month without approval.`
    : 'Work from home this month now needs approval.'
}
