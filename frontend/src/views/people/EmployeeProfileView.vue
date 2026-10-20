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

<!-- One employee record: /people/:userId, or the caller's own at
     /me/profile ("My details"). -->
<template>
  <div class="pa-6 profile">
    <v-btn
      v-if="!isOwn && canViewEmployees"
      variant="text"
      size="small"
      prepend-icon="mdi-arrow-left"
      class="mb-2"
      :to="{ name: 'employees' }"
    >
      Employees
    </v-btn>

    <v-progress-linear v-if="store.loading" indeterminate color="primary" />

    <AppCallout
      v-else-if="store.error"
      :variant="isOwn && store.errorStatus === 404 ? 'info' : 'error'"
      class="mb-4"
    >
      {{ store.error }}
    </AppCallout>

    <template v-else-if="record">
      <EmployeeHeaderCard :record="record" />
      <v-tabs v-model="tab" color="primary" density="compact" slider-color="primary" class="mb-4">
        <v-tab v-if="record.personal" value="personal">Personal</v-tab>
        <v-tab value="employment">Employment</v-tab>
        <v-tab v-if="showLeave" value="leave">Leave</v-tab>
        <v-tab v-if="showDetails" value="bank">Bank &amp; IDs</v-tab>
        <v-tab v-if="showDocuments" value="documents">Documents</v-tab>
      </v-tabs>
      <v-card color="surface" rounded="lg" class="pa-6">
        <v-tabs-window v-model="tab">
          <v-tabs-window-item v-if="record.personal" value="personal">
            <PersonalTab :employee-id="record.user_id" :personal="record.personal" :mode="personalMode" />
          </v-tabs-window-item>
          <v-tabs-window-item value="employment">
            <EmploymentTab :record="record" />
          </v-tabs-window-item>
          <v-tabs-window-item v-if="showLeave" value="leave">
            <MemberLeaveTab :user-id="record.user_id" />
          </v-tabs-window-item>
          <v-tabs-window-item v-if="showDetails" value="bank">
            <BankIdsTab :user-id="record.user_id" :is-own="isOwn" />
          </v-tabs-window-item>
          <v-tabs-window-item v-if="showDocuments" value="documents">
            <DocumentsTab :user-id="record.user_id" />
          </v-tabs-window-item>
        </v-tabs-window>
      </v-card>
    </template>
  </div>
</template>

<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { useRoute } from 'vue-router'
import AppCallout from '@/components/common/AppCallout.vue'
import BankIdsTab from '@/components/people/BankIdsTab.vue'
import DocumentsTab from '@/components/people/DocumentsTab.vue'
import EmployeeHeaderCard from '@/components/people/EmployeeHeaderCard.vue'
import EmploymentTab from '@/components/people/EmploymentTab.vue'
import MemberLeaveTab from '@/components/leave/MemberLeaveTab.vue'
import PersonalTab from '@/components/people/PersonalTab.vue'
import { usePermissions } from '@/composables/usePermissions'
import { useAuthStore } from '@/stores/auth'
import { useEmployeesStore } from '@/stores/employees'

const route = useRoute()
const store = useEmployeesStore()
const authStore = useAuthStore()
const {
  canViewEmployees,
  canApproveLeave,
  canViewLeaveReports,
  canManageEmployees,
  canSeeEmployeeDocuments,
} = usePermissions()

const routeUserId = computed(() => route.params.userId as string | undefined)
const isOwn = computed(() => !routeUserId.value || routeUserId.value === authStore.user?.id)
const record = computed(() => store.record)
const tab = ref('personal')
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

watch(
  () => routeUserId.value,
  async userId => {
    await store.fetchRecord(userId && !isOwn.value ? userId : 'me')
    tab.value = store.record?.personal ? 'personal' : 'employment'
  },
  { immediate: true },
)
</script>

<style scoped>
.profile {
  max-width: 1120px;
}
</style>
