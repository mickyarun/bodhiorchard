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

<!-- Add or edit an office. Its leave policy is what people placed there
     move onto; only people who manage leave can set it. -->
<template>
  <v-dialog :model-value="modelValue" max-width="520" :fullscreen="xs" @update:model-value="emit('update:modelValue', $event)">
    <v-card color="surface" rounded="lg">
      <div class="d-flex align-start ga-2 pa-6 pb-4">
        <div class="flex-grow-1">
          <h2 class="text-h6 font-weight-bold">{{ office ? 'Edit office' : 'Add office' }}</h2>
          <p class="text-body-2 text-medium-emphasis">Where people work from. Remote people have no office.</p>
        </div>
        <v-btn icon="mdi-close" variant="text" size="small" aria-label="Close" @click="close" />
      </div>
      <v-form class="px-6 pb-2 d-flex flex-column ga-4" @submit.prevent="submit">
        <v-text-field v-model="draft.name" label="Name" maxlength="100" autofocus v-bind="FIELD" />
        <div class="place-row">
          <v-text-field v-model="draft.city" label="City" maxlength="100" v-bind="FIELD" />
          <v-text-field v-model="draft.country_code" label="Country" placeholder="e.g. GB" persistent-placeholder maxlength="2" v-bind="FIELD" />
        </div>
        <v-select
          v-model="draft.leave_policy_id"
          :items="policyItems"
          label="Leave policy"
          clearable
          :disabled="!canConfigureLeave"
          :hint="policyHint"
          persistent-hint
          v-bind="FIELD"
        />
        <AppCallout v-if="error" variant="error">{{ error }}</AppCallout>
      </v-form>
      <v-divider class="mt-4" />
      <div class="d-flex justify-end ga-2 pa-4">
        <v-btn variant="text" @click="close">Cancel</v-btn>
        <v-btn color="primary" variant="flat" :loading="saving" :disabled="!draft.name.trim()" @click="submit">
          {{ office ? 'Save changes' : 'Add office' }}
        </v-btn>
      </div>
    </v-card>
  </v-dialog>
</template>

<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { useDisplay } from 'vuetify'
import AppCallout from '@/components/common/AppCallout.vue'
import { usePermissions } from '@/composables/usePermissions'
import { useLeavePoliciesStore } from '@/stores/leavePolicies'
import { useOfficesStore } from '@/stores/offices'
import type { OfficeRead, OfficeWrite } from '@/types/office'
import { blankToNull } from '@/utils/employee'

const props = defineProps<{ modelValue: boolean; office: OfficeRead | null }>()
const emit = defineEmits<{ 'update:modelValue': [value: boolean] }>()

const FIELD = { variant: 'outlined', density: 'compact', hideDetails: 'auto' } as const
const store = useOfficesStore()
const policies = useLeavePoliciesStore()
const { canConfigureLeave } = usePermissions()
const { xs } = useDisplay()
const draft = ref<OfficeWrite>(blank())
const saving = ref(false)
const error = ref('')

// Without leave rights the list can't load, so show the current policy alone.
const policyItems = computed(() => {
  if (canConfigureLeave.value) return policies.policies.map(p => ({ title: p.name, value: p.id }))
  const current = props.office
  return current?.leave_policy_id ? [{ title: current.leave_policy_name ?? '', value: current.leave_policy_id }] : []
})

const policyHint = computed(() =>
  canConfigureLeave.value
    ? 'People placed here move onto this policy. You can still change one person after.'
    : 'Ask someone who manages leave to set this.',
)

function blank(): OfficeWrite {
  return { name: '', city: null, country_code: null, leave_policy_id: null }
}

watch(
  () => props.modelValue,
  open => {
    if (!open) return
    const office = props.office
    draft.value = office
      ? { name: office.name, city: office.city, country_code: office.country_code, leave_policy_id: office.leave_policy_id }
      : blank()
    error.value = ''
    if (canConfigureLeave.value && !policies.policies.length) void policies.fetchPolicies()
  },
)

function close(): void {
  emit('update:modelValue', false)
}

async function submit(): Promise<void> {
  if (!draft.value.name.trim()) return
  saving.value = true
  const body = blankToNull({ ...draft.value, name: draft.value.name.trim() })
  error.value = (await store.saveOffice(body, props.office?.id ?? null)) ?? ''
  saving.value = false
  if (!error.value) close()
}
</script>

<style scoped>
.place-row {
  display: grid;
  grid-template-columns: minmax(0, 1fr) 160px;
  gap: 16px;
}
@media (max-width: 600px) {
  .place-row {
    grid-template-columns: 1fr;
  }
}
</style>
