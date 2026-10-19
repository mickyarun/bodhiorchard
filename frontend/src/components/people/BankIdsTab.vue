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

<!-- Bank & IDs: masked addresses, IDs and bank details, with Show for one
     value at a time, and who has looked at or changed them. -->
<template>
  <section>
    <v-progress-linear v-if="details.loading.value" indeterminate color="primary" class="mb-4" />
    <AppCallout v-if="details.error.value" variant="error" class="mb-4">{{ details.error.value }}</AppCallout>
    <template v-if="data">
      <div class="d-flex align-center justify-space-between flex-wrap ga-3 mb-2">
        <p class="text-body-2 text-medium-emphasis">
          Encrypted. Only HR and {{ isOwn ? 'you' : 'this person' }} can see these, one value at a time.
        </p>
        <v-btn v-if="data.can_edit" variant="tonal" size="small" prepend-icon="mdi-pencil-outline" @click="editing = true">
          Edit
        </v-btn>
      </div>
      <div v-for="group in GROUPS" :key="group.title" class="mb-6">
        <div class="text-overline text-medium-emphasis">{{ group.title }}</div>
        <div v-if="group.title === 'Bank'" class="plain-row">
          <span class="text-caption text-medium-emphasis">Bank / IFSC</span>
          <span>{{ [data.bank_name, data.bank_ifsc].filter(Boolean).join(' · ') || '—' }}</span>
        </div>
        <SensitiveValueRow
          v-for="field in group.fields"
          :key="field"
          :label="FIELD_LABELS[field]"
          :value="data[field]"
          :can-reveal="data.can_reveal"
          :reveal="() => revealAndLog(field)"
        />
      </div>
      <h3 class="text-subtitle-2 font-weight-bold mb-2">Who has looked at or changed these</h3>
      <AccessLogList :user-id="userId" :version="logVersion" />
    </template>
    <SensitiveEditDialog v-model="editing" :save="saveAndLog" />
  </section>
</template>

<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import AppCallout from '@/components/common/AppCallout.vue'
import AccessLogList from '@/components/people/AccessLogList.vue'
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
.plain-row {
  display: grid;
  grid-template-columns: 180px minmax(0, 1fr);
  gap: 16px;
  padding: 10px 0;
  border-bottom: 1px solid rgb(var(--v-border-color), var(--v-border-opacity));
}
</style>
