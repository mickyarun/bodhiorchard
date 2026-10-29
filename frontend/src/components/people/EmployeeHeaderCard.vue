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

<!-- Top of an employee profile: who they are, their role, and where
     they sit (code, managers, joining date and tenure, office or remote). -->
<template>
  <section class="summary" aria-label="Profile summary">
    <EmployeeAvatar
      :user-id="record.user_id"
      :name="record.name"
      :avatar-url="record.avatar_url"
      :editable="record.can_edit_avatar"
      :size="88"
      @updated="emit('avatar-updated', $event)"
      @error="emit('avatar-error', $event)"
    />
    <div class="summary__main">
      <div class="summary__title">
        <h1 class="summary__name">{{ record.name }}</h1>
        <EmployeeStatusChip :status="record.work.status" show-active />
        <span class="summary__tag">{{ EMPLOYMENT_TYPE_LABELS[record.work.employment_type] }}</span>
        <v-chip v-if="!record.is_active" size="small" variant="tonal" color="error">Account deactivated</v-chip>
      </div>
      <p class="summary__role">{{ roleLine }}</p>
      <div class="summary__meta">
        <span v-if="record.work.employee_code" class="summary__code">{{ record.work.employee_code }}</span>
        <span v-if="primary">
          Reports to
          <router-link v-if="canViewEmployees" :to="{ name: 'employee-profile', params: { userId: primary.user_id } }">
            {{ primary.name }}</router-link><template v-else>{{ primary.name }}</template>{{ extraManagers }}
        </span>
        <span v-else>No manager set</span>
        <span v-if="joined">{{ joined }}</span>
        <span>{{ workplaceLabel(record.work.work_arrangement, record.office) }}</span>
      </div>
    </div>
    <div class="summary__actions">
      <v-btn v-if="record.access.edit_name" variant="outlined" prepend-icon="mdi-pencil-outline" @click="editingName = true">
        Edit name
      </v-btn>
      <slot name="actions" />
    </div>
    <EditNameDialog v-model="editingName" :user-id="record.user_id" :current="record.name" />
  </section>
</template>

<script setup lang="ts">
import { computed, ref } from 'vue'
import EditNameDialog from '@/components/people/EditNameDialog.vue'
import EmployeeAvatar from '@/components/people/EmployeeAvatar.vue'
import EmployeeStatusChip from '@/components/people/EmployeeStatusChip.vue'
import { usePermissions } from '@/composables/usePermissions'
import type { EmployeeRecord } from '@/types/employee'
import { EMPLOYMENT_TYPE_LABELS, formatDateOnly, workplaceLabel } from '@/utils/employee'
import { tenureFor } from '@/utils/employeeProfile'

const props = defineProps<{ record: EmployeeRecord }>()
const editingName = ref(false)
const { canViewEmployees } = usePermissions()

const emit = defineEmits<{
  /** New photo URL, or null after a removal. */
  'avatar-updated': [avatarUrl: string | null]
  'avatar-error': [message: string]
}>()

const roleLine = computed(
  () =>
    [props.record.work.designation, props.record.work.department].filter(Boolean).join(' · ') ||
    props.record.email,
)

const primary = computed(() => props.record.managers.find(m => m.is_primary) ?? null)
const extraManagers = computed(() =>
  props.record.managers.length > 1 ? ` +${props.record.managers.length - 1}` : '',
)

/** "Joined 10 Jan 2022 · 4 years 9 months". */
const joined = computed(() => {
  const date = props.record.work.date_of_joining
  if (!date) return ''
  const tenure = tenureFor(props.record.work, new Date())
  return [`Joined ${formatDateOnly(date)}`, tenure].filter(Boolean).join(' · ')
})
</script>

<style scoped>
.summary {
  background: rgb(var(--v-theme-surface));
  border: 1px solid rgb(var(--v-theme-rule));
  border-radius: 14px;
  padding: 24px;
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 16px 22px;
  min-width: 0;
}
.summary__main {
  flex: 1 1 360px;
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: 8px;
}
.summary__title {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 6px 10px;
}
.summary__name {
  margin: 0;
  font-size: 26px;
  line-height: 32px;
  font-weight: 600;
  letter-spacing: var(--tracking-display);
  overflow-wrap: anywhere;
}
.summary__tag {
  font-size: 12px;
  font-weight: 500;
  padding: 3px 10px;
  border-radius: var(--radius-pill);
  background: rgb(var(--v-theme-surface-variant));
  color: rgb(var(--v-theme-ink-2));
}
.summary__role {
  margin: 0;
  font-size: 15px;
  color: rgb(var(--v-theme-ink-2));
}
.summary__meta {
  display: flex;
  flex-wrap: wrap;
  gap: 4px 16px;
  font-size: 13px;
  color: rgb(var(--v-theme-on-surface-variant));
}
.summary__meta a {
  color: var(--color-accent-text);
  /* Underlined, not colour alone: it sits inside a sentence. */
  text-decoration: underline;
  text-underline-offset: 2px;
}
.summary__code {
  font-family: var(--font-mono);
}
.summary__actions {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}
@media (max-width: 600px) {
  .summary {
    padding: 20px 16px;
  }
}
</style>
