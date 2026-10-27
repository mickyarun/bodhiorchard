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

<!-- The Name cell of a directory row: photo, name as a real link (so
     keyboards and screen readers can open the profile), status when not
     active, and email. -->
<template>
  <div class="person">
    <EmployeeAvatar :user-id="row.user_id" :name="row.name" :avatar-url="row.avatar_url" :size="34" />
    <div class="person__text">
      <div class="person__line">
        <router-link
          :to="{ name: 'employee-profile', params: { userId: row.user_id } }"
          class="person__name"
          @click.stop
        >
          {{ row.name }}
        </router-link>
        <EmployeeStatusChip :status="row.status" />
      </div>
      <div class="person__email">{{ row.email }}</div>
    </div>
  </div>
</template>

<script setup lang="ts">
import EmployeeAvatar from '@/components/people/EmployeeAvatar.vue'
import EmployeeStatusChip from '@/components/people/EmployeeStatusChip.vue'
import type { DirectoryEntry } from '@/types/employee'

defineProps<{ row: DirectoryEntry }>()
</script>

<style scoped>
.person {
  display: flex;
  align-items: center;
  gap: 12px;
  min-width: 0;
}
.person__text {
  min-width: 0;
}
.person__line {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 4px 8px;
}
.person__name {
  color: inherit;
  font-weight: 500;
  text-decoration: none;
}
.person__name:hover {
  text-decoration: underline;
}
.person__email {
  font-size: 12px;
  color: rgb(var(--v-theme-on-surface-variant));
  white-space: nowrap;
}
@media (max-width: 600px) {
  .person__email {
    white-space: normal;
    overflow-wrap: anywhere;
  }
}
</style>
