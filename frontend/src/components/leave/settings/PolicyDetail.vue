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

<!-- One policy's settings, split into tabs that each save on their own. -->
<template>
  <section>
    <div class="d-flex align-center ga-2 mb-4">
      <v-btn variant="text" size="small" prepend-icon="mdi-arrow-left" @click="emit('back')">
        All policies
      </v-btn>
    </div>
    <div class="d-flex align-center ga-2 mb-1">
      <h2 class="text-h6 font-weight-bold">{{ policy.name }}</h2>
      <v-chip v-if="policy.is_default" size="x-small" color="primary" variant="tonal" label>Default</v-chip>
    </div>
    <p class="text-body-2 text-medium-emphasis mb-4">{{ region || 'No country set' }}</p>
    <v-tabs v-model="tab" color="primary" density="compact" slider-color="primary" class="mb-4">
      <v-tab value="types">Leave types</v-tab>
      <v-tab value="holidays">Holidays</v-tab>
      <v-tab value="wfh">Work from home</v-tab>
      <v-tab value="joiners">New joiners</v-tab>
      <v-tab value="general">General</v-tab>
      <v-tab value="employees">Employees</v-tab>
    </v-tabs>
    <v-card color="surface" rounded="lg" class="pa-6">
      <v-tabs-window v-model="tab">
        <v-tabs-window-item value="types">
          <LeaveTypesTab :policy-id="policy.id" />
        </v-tabs-window-item>
        <v-tabs-window-item value="holidays">
          <HolidaysTab :policy="policy" />
        </v-tabs-window-item>
        <v-tabs-window-item value="wfh">
          <WfhTab :policy="policy" />
        </v-tabs-window-item>
        <v-tabs-window-item value="joiners">
          <NewJoinersTab :policy="policy" />
        </v-tabs-window-item>
        <v-tabs-window-item value="general">
          <GeneralTab :policy="policy" />
        </v-tabs-window-item>
        <v-tabs-window-item value="employees">
          <EmployeesTab :policy-id="policy.id" />
        </v-tabs-window-item>
      </v-tabs-window>
    </v-card>
  </section>
</template>

<script setup lang="ts">
import { ref } from 'vue'
import EmployeesTab from '@/components/leave/settings/EmployeesTab.vue'
import GeneralTab from '@/components/leave/settings/GeneralTab.vue'
import HolidaysTab from '@/components/leave/settings/HolidaysTab.vue'
import LeaveTypesTab from '@/components/leave/settings/LeaveTypesTab.vue'
import NewJoinersTab from '@/components/leave/settings/NewJoinersTab.vue'
import WfhTab from '@/components/leave/settings/WfhTab.vue'
import type { PolicyRead } from '@/types/leavePolicy'

defineProps<{ policy: PolicyRead; region: string }>()
const emit = defineEmits<(e: 'back') => void>()

const tab = ref('types')
</script>
