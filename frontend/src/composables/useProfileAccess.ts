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
 * Which parts of an employee profile the viewer gets. Mirrors the API's
 * rules; the API is still the authority and refuses anything else.
 */
import { computed, type Ref } from 'vue'

import { usePermissions } from '@/composables/usePermissions'
import { useAuthStore } from '@/stores/auth'
import type { EmployeeRecord } from '@/types/employee'
import { profileTabs } from '@/utils/employeeProfile'

export function useProfileAccess(record: Ref<EmployeeRecord | null>, isOwn: Ref<boolean>) {
  const authStore = useAuthStore()
  const { canApproveLeave, canViewLeaveReports, canManageEmployees, canSeeEmployeeDocuments } =
    usePermissions()

  // Balances are open to HR, the member and the member's managers (the
  // API enforces the same rule).
  const isManagerOfRecord = computed(
    () => !!record.value?.managers.some(m => m.user_id === authStore.user?.id),
  )
  const showLeave = computed(
    // Not leave:configure alone: balances reveal who used sick leave.
    () =>
      isOwn.value || canApproveLeave.value || canViewLeaveReports.value || isManagerOfRecord.value,
  )

  // HR (and the owner, who holds every permission) or the person themself;
  // the API enforces the same rules.
  const showDetails = computed(() => isOwn.value || canManageEmployees.value)
  const showDocuments = computed(() => isOwn.value || canSeeEmployeeDocuments.value)

  const personalMode = computed<'hr' | 'self' | 'view'>(() => {
    if (record.value?.access.edit_personal) return 'hr'
    return isOwn.value ? 'self' : 'view'
  })

  const tabs = computed(() =>
    profileTabs({
      personal: !!record.value?.personal,
      leave: showLeave.value,
      details: showDetails.value,
      documents: showDocuments.value,
    }),
  )

  return { showLeave, personalMode, tabs }
}
