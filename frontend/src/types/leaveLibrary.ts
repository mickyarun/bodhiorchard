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

/** The org's leave type library, mirroring backend/app/schemas/leave_library.py. */
import type { Decimalish } from '@/types/leave'
import type { LeaveTypeWrite } from '@/types/leavePolicy'

/** A library type's name, default quota and rules (no on/off: that's per policy). */
export type LibraryTypeWrite = Omit<LeaveTypeWrite, 'is_active'>

/** One policy that has the library type, with its quota there. */
export interface LibraryTypeUse {
  policy_id: string
  policy_name: string
  type_id: string
  own_quota: boolean
  annual_quota_days: Decimalish | null
  is_active: boolean
}

export interface LibraryTypeRead extends LibraryTypeWrite {
  id: string
  uses: LibraryTypeUse[]
}

/** What a policy sets on a library type. With own_quota off the library default applies. */
export interface LinkedTypeWrite {
  own_quota: boolean
  annual_quota_days: Decimalish | null
  is_active: boolean
}

/** Add a library type to a policy, or make a policy's own type follow it. */
export interface LibraryTypeAdd extends LinkedTypeWrite {
  template_id: string
}
