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

<!-- Sidebar links for the people workspace (leave, WFH, employee
     records), open to every member. The "People" heading only shows when
     the engineering links sit above it; on its own the group needs none. -->
<template>
  <v-list-subheader v-if="showHeading && !rail" class="people-nav__heading">
    People
  </v-list-subheader>
  <v-divider v-else-if="showHeading" class="my-2" />
  <v-list-item
    prepend-icon="mdi-beach"
    title="Leave"
    to="/leave"
    exact
    rounded="lg"
  />
  <v-list-item
    prepend-icon="mdi-calendar-month-outline"
    title="Team calendar"
    to="/leave/team"
    rounded="lg"
  />
  <v-list-item
    v-if="leaveStore.approvalCount.is_approver"
    prepend-icon="mdi-check-decagram-outline"
    title="Leave approvals"
    to="/leave/approvals"
    rounded="lg"
  >
    <template v-if="leaveStore.approvalCount.pending > 0 && !rail" #append>
      <span class="people-nav__pill" :aria-label="`${leaveStore.approvalCount.pending} pending`">
        {{ leaveStore.approvalCount.pending }}
      </span>
    </template>
  </v-list-item>
  <v-list-item
    v-if="canViewLeaveReports || leaveStore.approvalCount.is_approver"
    prepend-icon="mdi-file-chart-outline"
    title="Leave reports"
    to="/leave/reports"
    rounded="lg"
  />
  <v-list-item
    v-if="canViewEmployees"
    prepend-icon="mdi-card-account-details-outline"
    title="Employees"
    to="/people"
    rounded="lg"
  />
  <v-list-item
    prepend-icon="mdi-account-box-outline"
    title="My details"
    to="/me/profile"
    rounded="lg"
  />
</template>

<script setup lang="ts">
import { onMounted } from 'vue'
import { usePermissions } from '@/composables/usePermissions'
import { useLeaveStore } from '@/stores/leave'

defineProps<{ rail: boolean; showHeading: boolean }>()

const { canViewEmployees, canViewLeaveReports } = usePermissions()
const leaveStore = useLeaveStore()

onMounted(() => {
  void leaveStore.fetchApprovalCount()
})
</script>

<style scoped>
.people-nav__heading {
  font-size: 10px;
  font-weight: 600;
  letter-spacing: var(--tracking-label, 0.08em);
  text-transform: uppercase;
  color: rgb(var(--v-theme-muted));
  margin-top: 16px;
}
.people-nav__pill {
  min-width: 20px;
  height: 20px;
  padding: 0 6px;
  border-radius: 999px;
  font-size: 11px;
  font-weight: 600;
  line-height: 20px;
  text-align: center;
  background: rgb(var(--v-theme-primary));
  color: rgb(var(--v-theme-on-primary));
}
</style>
