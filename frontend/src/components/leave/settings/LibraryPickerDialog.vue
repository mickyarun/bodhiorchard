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

<!-- Add a type from the org's library to a policy. When the policy already
     has its own type of that name or code, the choice is to make that one
     follow the library instead, so its requests and balances carry on. -->
<template>
  <v-dialog :model-value="modelValue" max-width="600" :fullscreen="xs" scrollable @update:model-value="emit('update:modelValue', $event)">
    <v-card color="surface" rounded="lg">
      <div class="d-flex align-start ga-2 pa-6 pb-2">
        <div class="flex-grow-1">
          <h2 class="text-h6 font-weight-bold">Add from library</h2>
          <p class="text-body-2 text-medium-emphasis">Its rules stay in step with the library. {{ policy.name }} can keep its own yearly quota.</p>
        </div>
        <v-btn icon="mdi-close" variant="text" size="small" aria-label="Close" @click="close" />
      </div>
      <v-card-text class="px-6">
        <AppCallout v-if="library.error" variant="error" class="mb-4">{{ library.error }}</AppCallout>
        <LeaveEmptyState
          v-if="!library.loading && !choices.length && !library.error"
          icon="mdi-bookshelf"
          title="The library is empty"
          body="Add leave types to the library once, then add them to any policy."
        >
          <template #actions>
            <v-btn color="primary" variant="flat" @click="openLibrary">Open the library</v-btn>
          </template>
        </LeaveEmptyState>
        <v-radio-group v-else v-model="selectedId" hide-details aria-label="Library type">
          <v-radio v-for="c in choices" :key="c.entry.id" :value="c.entry.id" :disabled="c.onPolicy" class="mb-1">
            <template #label>
              <span class="font-weight-medium">{{ c.entry.name }}</span>
              <span class="text-caption text-medium-emphasis ml-2">{{ c.onPolicy ? 'Already on this policy' : allowanceLabel(c.entry) }}</span>
            </template>
          </v-radio>
        </v-radio-group>
        <template v-if="selected">
          <AppCallout v-if="selected.ownMatch" variant="info" class="mt-4">
            {{ policy.name }} already has its own {{ selected.ownMatch.name }} ({{ selected.ownMatch.code }}). It will follow the library from now on, keeping its requests and balances, and take the library's name and rules.
          </AppCallout>
          <div class="text-overline text-medium-emphasis mt-4 mb-2">Yearly quota on this policy</div>
          <LinkedQuotaField v-model:choice="choice" v-model:days="days" :library-quota="selected.entry.annual_quota_days" :auto-approve="selected.entry.auto_approve" />
        </template>
        <AppCallout v-if="error" variant="error" class="mt-3">{{ error }}</AppCallout>
      </v-card-text>
      <v-divider />
      <div class="d-flex justify-end ga-2 pa-4">
        <v-btn variant="text" @click="close">Cancel</v-btn>
        <v-btn color="primary" variant="flat" :loading="saving" :disabled="!selected || !validLinkQuota(choice, days)" @click="submit">
          {{ selected?.ownMatch ? 'Follow the library' : 'Add to policy' }}
        </v-btn>
      </div>
    </v-card>
  </v-dialog>
</template>

<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import { useDisplay } from 'vuetify'
import AppCallout from '@/components/common/AppCallout.vue'
import LeaveEmptyState from '@/components/leave/settings/LeaveEmptyState.vue'
import LinkedQuotaField from '@/components/leave/settings/LinkedQuotaField.vue'
import { useLeaveLibraryStore } from '@/stores/leaveLibrary'
import { useLeavePolicyConfigStore } from '@/stores/leavePolicyConfig'
import type { PolicyRead } from '@/types/leavePolicy'
import { toNumberOrNull } from '@/utils/leave'
import { type QuotaChoice, libraryChoices, linkBody, validLinkQuota } from '@/utils/leaveLibrary'
import { allowanceLabel } from '@/utils/leavePolicyDisplay'

const props = defineProps<{ modelValue: boolean; policy: PolicyRead }>()
const emit = defineEmits<(e: 'update:modelValue', value: boolean) => void>()

const library = useLeaveLibraryStore()
const policyTypes = useLeavePolicyConfigStore()
const router = useRouter()
const { xs } = useDisplay()
const selectedId = ref<string | null>(null)
const choice = ref<QuotaChoice>('library')
const days = ref<number | null>(null)
const saving = ref(false)
const error = ref('')

const choices = computed(() => libraryChoices(library.entries, policyTypes.types))
const selected = computed(() => choices.value.find(c => c.entry.id === selectedId.value) ?? null)

watch(
  () => props.modelValue,
  open => {
    if (!open) return
    selectedId.value = null
    error.value = ''
    void library.fetchEntries()
  },
)

// Linking the policy's own type keeps its quota unless it already matches the library's.
// Keyed on the id: a reload of the lists mustn't undo what the user chose since.
watch(selectedId, () => {
  const picked = selected.value
  const own = picked?.ownMatch
  const ownDays = own ? toNumberOrNull(own.annual_quota_days) : null
  const same = !own || ownDays === toNumberOrNull(picked?.entry.annual_quota_days ?? null)
  choice.value = same ? 'library' : ownDays === null ? 'unlimited' : 'fixed'
  days.value = ownDays
})

function close(): void {
  emit('update:modelValue', false)
}

async function submit(): Promise<void> {
  const picked = selected.value
  if (!picked) return
  saving.value = true
  const body = { ...linkBody(choice.value, days.value, true), template_id: picked.entry.id }
  error.value =
    (picked.ownMatch
      ? await library.linkExisting(picked.ownMatch, { ...body, is_active: picked.ownMatch.is_active })
      : await library.addToPolicy(props.policy.id, body)) ?? ''
  saving.value = false
  if (!error.value) close()
}

function openLibrary(): void {
  close()
  void router.replace({ query: { view: 'types' } })
}
</script>
