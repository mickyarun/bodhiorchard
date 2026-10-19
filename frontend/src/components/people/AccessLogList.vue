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

<!-- The access log for one person: who revealed, changed, uploaded,
     opened or deleted their sensitive details and documents. -->
<template>
  <AppCallout v-if="error" variant="error">{{ error }}</AppCallout>
  <p v-else-if="!loading && !entries.length" class="text-body-2 text-medium-emphasis">Nobody yet.</p>
  <v-list v-else density="compact" bg-color="transparent" class="pa-0">
    <v-list-item v-for="(entry, i) in entries" :key="i" class="px-0">
      <v-list-item-title class="text-body-2">{{ accessLine(entry) }}</v-list-item-title>
      <v-list-item-subtitle class="text-caption">{{ formatDateTime(entry.at) }}</v-list-item-subtitle>
    </v-list-item>
  </v-list>
</template>

<script setup lang="ts">
import { ref, watch } from 'vue'
import AppCallout from '@/components/common/AppCallout.vue'
import api from '@/services/api'
import type { AccessLogEntry } from '@/types/employeeRecords'
import { formatDateTime } from '@/utils/date'
import { accessLine } from '@/utils/employeeRecords'
import { extractApiError } from '@/utils/errors'

// ``version`` changes when the parent knows a new entry was just written.
const props = defineProps<{ userId: string; version?: number }>()
const entries = ref<AccessLogEntry[]>([])
const loading = ref(false)
const error = ref('')

async function load(): Promise<void> {
  loading.value = true
  error.value = ''
  try {
    entries.value = (await api.get<AccessLogEntry[]>(`/v1/employees/${props.userId}/access-log`)).data
  } catch (err) {
    error.value = extractApiError(err, "Couldn't load the access log.")
  } finally {
    loading.value = false
  }
}

watch(() => [props.userId, props.version], () => void load(), { immediate: true })
</script>
