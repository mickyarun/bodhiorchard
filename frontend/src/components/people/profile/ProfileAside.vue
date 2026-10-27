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

<!-- Side column of the profile's overview tab: leave left this year (for
     those who may see balances), the team, and what's coming up. -->
<template>
  <aside class="profile-aside" aria-label="At a glance">
    <LeaveSummaryPanel v-if="showLeave" :user-id="record.user_id" @details="emit('leave-details')" />
    <TeamPanel :record="record" />
    <ComingUpPanel :record="record" />
  </aside>
</template>

<script setup lang="ts">
import ComingUpPanel from '@/components/people/profile/ComingUpPanel.vue'
import LeaveSummaryPanel from '@/components/people/profile/LeaveSummaryPanel.vue'
import TeamPanel from '@/components/people/profile/TeamPanel.vue'
import type { EmployeeRecord } from '@/types/employee'

defineProps<{ record: EmployeeRecord; showLeave: boolean }>()
const emit = defineEmits<{ 'leave-details': [] }>()
</script>

<style scoped>
.profile-aside {
  display: flex;
  flex-direction: column;
  gap: 20px;
  min-width: 0;
}
</style>
