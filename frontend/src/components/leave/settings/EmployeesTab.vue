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

<!-- Who follows this policy, and moving members onto it. -->
<template>
  <section>
    <v-form class="move-row mb-4" @submit.prevent="move">
      <v-autocomplete
        v-model="selected"
        :items="candidates"
        item-title="name"
        item-value="id"
        label="Move employees here"
        multiple
        chips
        closable-chips
        :loading="directory.loading.value"
        v-bind="field"
      >
        <template #item="{ props: itemProps, item }">
          <v-list-item v-bind="itemProps" :subtitle="item.raw.email" />
        </template>
      </v-autocomplete>
      <v-btn type="submit" color="primary" variant="tonal" :loading="moving" :disabled="!selected.length">
        Move
      </v-btn>
    </v-form>
    <AppCallout v-if="error" variant="error" class="mb-3">{{ error }}</AppCallout>
    <AppCallout v-else-if="movedText" variant="success" class="mb-3">{{ movedText }}</AppCallout>
    <p v-if="!store.employees.length" class="text-body-2 text-medium-emphasis">
      Nobody is on this policy yet.
    </p>
    <v-list v-else bg-color="transparent" density="compact">
      <v-list-item v-for="person in store.employees" :key="person.user_id" :title="person.name" prepend-icon="mdi-account-outline" />
    </v-list>
  </section>
</template>

<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import AppCallout from '@/components/common/AppCallout.vue'
import { useMemberDirectory } from '@/composables/useMemberDirectory'
import { useLeavePoliciesStore } from '@/stores/leavePolicies'
import { movedSummary } from '@/utils/leavePolicy'

const props = defineProps<{ policyId: string }>()

const store = useLeavePoliciesStore()
const directory = useMemberDirectory()
const field = { variant: 'outlined', density: 'compact', hideDetails: 'auto' } as const
const selected = ref<string[]>([])
const moving = ref(false)
const error = ref('')
const movedText = ref('')

const candidates = computed(() => {
  const onPolicy = new Set(store.employees.map(e => e.user_id))
  return directory.entries.value.filter(m => !onPolicy.has(m.id))
})

async function move(): Promise<void> {
  if (!selected.value.length) return
  moving.value = true
  const result = await store.assign(props.policyId, selected.value)
  moving.value = false
  if (typeof result === 'string') {
    error.value = result
    return
  }
  error.value = ''
  movedText.value = movedSummary(result)
  selected.value = []
}

watch(
  () => props.policyId,
  async id => {
    selected.value = []
    movedText.value = ''
    error.value = (await store.fetchEmployees(id)) ?? ''
  },
  { immediate: true },
)

onMounted(() => {
  void directory.ensureLoaded()
})
</script>

<style scoped>
.move-row {
  display: grid;
  grid-template-columns: minmax(0, 1fr) auto;
  align-items: start;
  gap: 12px;
}
</style>
