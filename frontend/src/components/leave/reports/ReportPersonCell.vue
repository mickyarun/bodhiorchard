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

<!-- Who a report row is about: name (a link to their record for those who
     can open it), code and department. -->
<template>
  <div>
    <router-link
      v-if="canViewEmployees"
      :to="{ name: 'employee-profile', params: { userId: row.user_id } }"
      class="font-weight-medium name"
    >
      {{ row.name }}
    </router-link>
    <span v-else class="font-weight-medium text-no-wrap">{{ row.name }}</span>
    <div class="text-caption text-medium-emphasis text-no-wrap">{{ caption }}</div>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { usePermissions } from '@/composables/usePermissions'

const props = defineProps<{
  row: { user_id: string; name: string; employee_code: string | null; department: string | null }
}>()
const { canViewEmployees } = usePermissions()
const caption = computed(() => [props.row.employee_code, props.row.department].filter(Boolean).join(' · '))
</script>

<style scoped>
.name {
  color: inherit;
  text-decoration: none;
  white-space: nowrap;
}
.name:hover {
  text-decoration: underline;
}
</style>
