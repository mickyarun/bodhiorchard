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

<!-- Bank and IDs: masked addresses, IDs and bank details, with Reveal for
     one value at a time, and who has looked at or changed them. -->
<template>
  <section class="bank-ids">
    <v-progress-linear v-if="details.loading.value" indeterminate color="primary" />
    <AppCallout v-if="details.error.value" variant="error">{{ details.error.value }}</AppCallout>
    <template v-if="data">
      <div class="bank-ids__intro">
        <p>
          <v-icon icon="mdi-lock-outline" size="16" class="mr-1" />
          Encrypted. Only HR and {{ isOwn ? 'you' : 'this person' }} can see these, one value at a time.
        </p>
        <v-btn v-if="data.can_edit" variant="outlined" size="small" prepend-icon="mdi-pencil-outline" @click="editing = true">
          Edit
        </v-btn>
      </div>
      <ProfileCards>
        <AppPanel v-for="group in GROUPS" :key="group.title" :title="group.title">
          <div class="bank-ids__rows">
            <FieldGrid v-if="group.title === 'Bank'" :fields="bankFields" />
            <SensitiveValueRow
              v-for="field in group.fields"
              :key="field"
              :label="FIELD_LABELS[field]"
              :value="data[field]"
              :can-reveal="data.can_reveal"
              :reveal="() => revealAndLog(field)"
            />
          </div>
        </AppPanel>
        <AppPanel title="Access log" note="Who has looked at or changed these">
          <AccessLogList :user-id="userId" :version="logVersion" />
        </AppPanel>
      </ProfileCards>
    </template>
    <SensitiveEditDialog v-model="editing" :save="saveAndLog" />
  </section>
</template>

<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import AppCallout from '@/components/common/AppCallout.vue'
import AppPanel from '@/components/common/AppPanel.vue'
import AccessLogList from '@/components/people/AccessLogList.vue'
import FieldGrid, { type GridField } from '@/components/people/FieldGrid.vue'
import ProfileCards from '@/components/people/profile/ProfileCards.vue'
import SensitiveEditDialog from '@/components/people/SensitiveEditDialog.vue'
import SensitiveValueRow from '@/components/people/SensitiveValueRow.vue'
import { useSensitiveDetails } from '@/composables/useSensitiveDetails'
import type { SensitiveField, SensitiveWrite } from '@/types/employeeRecords'
import { FIELD_LABELS } from '@/utils/employeeRecords'

const GROUPS: { title: string; fields: SensitiveField[] }[] = [
  { title: 'Bank', fields: ['bank_account_number'] },
  { title: 'IDs', fields: ['pan', 'aadhaar', 'passport_number'] },
  { title: 'Addresses', fields: ['current_address', 'permanent_address'] },
]

const props = defineProps<{ userId: string; isOwn: boolean }>()
const details = useSensitiveDetails(() => props.userId)
const data = computed(() => details.data.value)
const bankFields = computed<GridField[]>(() => [
  {
    label: 'Bank and IFSC',
    value: [data.value?.bank_name, data.value?.bank_ifsc].filter(Boolean).join(' · ') || null,
  },
])
const editing = ref(false)
// Bumped after each save or reveal so the access log shows it straight away.
const logVersion = ref(0)

async function revealAndLog(field: SensitiveField) {
  const result = await details.reveal(field)
  logVersion.value += 1
  return result
}

async function saveAndLog(body: SensitiveWrite): Promise<string | null> {
  const error = await details.save(body)
  if (!error) logVersion.value += 1
  return error
}

watch(() => props.userId, () => void details.load(), { immediate: true })
</script>

<style scoped>
.bank-ids {
  display: flex;
  flex-direction: column;
  gap: 20px;
  min-width: 0;
}
.bank-ids__intro {
  display: flex;
  align-items: center;
  justify-content: space-between;
  flex-wrap: wrap;
  gap: 8px 16px;
}
.bank-ids__intro p {
  margin: 0;
  font-size: 14px;
  color: rgb(var(--v-theme-on-surface-variant));
}
.bank-ids__rows {
  display: flex;
  flex-direction: column;
  gap: 12px;
}
</style>
