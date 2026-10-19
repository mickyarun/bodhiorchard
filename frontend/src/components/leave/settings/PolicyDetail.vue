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

<!-- One policy: its details in the header, and a section at a time
     (`?section=`) beside the section list. -->
<template>
  <section :aria-label="policy.name">
    <v-btn variant="text" size="small" prepend-icon="mdi-arrow-left" class="mb-3 ml-n2" @click="emit('back')">
      All policies
    </v-btn>
    <header class="detail-head mb-6">
      <div class="shrink">
        <div class="d-flex align-center flex-wrap ga-2">
          <h2 class="text-h5 font-weight-bold">{{ policy.name }}</h2>
          <v-chip v-if="policy.is_default" size="small" color="primary" variant="tonal" label>Default</v-chip>
        </div>
        <p class="text-body-2 text-medium-emphasis mt-1">{{ region || 'No country set' }} · {{ policy.timezone }}</p>
      </div>
      <v-btn variant="tonal" prepend-icon="mdi-pencil-outline" @click="editing = true">Edit details</v-btn>
    </header>

    <div class="detail-body">
      <PolicySectionNav v-model="section" :people="policy.employee_count" />
      <div class="shrink">
        <LeaveTypesSection v-if="section === 'types'" :policy="policy" />
        <HolidaysSection v-else-if="section === 'holidays'" :policy="policy" @edit-details="editing = true" />
        <PolicyRulesSection v-else-if="section === 'rules'" :policy="policy" />
        <PolicyPeopleSection v-else-if="section === 'people'" :policy="policy" />
        <PolicyHistorySection v-else :policy-id="policy.id" />
      </div>
    </div>

    <PolicyDetailsDialog v-model="editing" :policy="policy" @saved="saved = true" />
    <v-snackbar v-model="saved" :timeout="2500" location="bottom">Saved</v-snackbar>
  </section>
</template>

<script setup lang="ts">
import { computed, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import HolidaysSection from '@/components/leave/settings/HolidaysSection.vue'
import LeaveTypesSection from '@/components/leave/settings/LeaveTypesSection.vue'
import PolicyDetailsDialog from '@/components/leave/settings/PolicyDetailsDialog.vue'
import PolicyHistorySection from '@/components/leave/settings/PolicyHistorySection.vue'
import PolicyPeopleSection from '@/components/leave/settings/PolicyPeopleSection.vue'
import PolicyRulesSection from '@/components/leave/settings/PolicyRulesSection.vue'
import PolicySectionNav from '@/components/leave/settings/PolicySectionNav.vue'
import type { PolicyRead } from '@/types/leavePolicy'
import { parseSection, type PolicySection } from '@/utils/leavePolicyDisplay'

defineProps<{ policy: PolicyRead; region: string }>()
const emit = defineEmits<(e: 'back') => void>()

const route = useRoute()
const router = useRouter()
const editing = ref(false)
const saved = ref(false)

const section = computed<PolicySection>({
  get: () => parseSection(route.query.section),
  set: value => {
    void router.replace({ query: { ...route.query, section: value } })
  },
})
</script>

<style scoped>
.shrink {
  min-width: 0;
}
.detail-head {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  flex-wrap: wrap;
  gap: 12px;
}
.detail-body {
  display: grid;
  grid-template-columns: 220px minmax(0, 1fr);
  gap: 32px;
}
@media (max-width: 959px) {
  .detail-body {
    grid-template-columns: minmax(0, 1fr);
    gap: 0;
  }
}
</style>
