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

<!-- Add or edit a leave type. Types are switched off, never deleted, so
     past requests keep their meaning. -->
<template>
  <v-dialog :model-value="modelValue" max-width="480" @update:model-value="emit('update:modelValue', $event)">
    <v-card class="pa-0">
      <div class="d-flex align-center justify-space-between pa-6 pb-2">
        <h2 class="text-h6 font-weight-bold">{{ type ? 'Edit leave type' : 'Add leave type' }}</h2>
        <v-btn icon="mdi-close" variant="text" size="small" aria-label="Close" @click="close" />
      </div>
      <v-form class="px-6 d-flex flex-column ga-3" @submit.prevent="submit">
        <div class="form-grid">
          <v-text-field v-model="draft.name" label="Name" autofocus v-bind="field" @update:model-value="syncCode" />
          <v-text-field v-model="draft.code" label="Code" maxlength="10" v-bind="field" @update:model-value="codeTouched = true" />
        </div>
        <div class="d-flex align-center ga-4 flex-wrap">
          <v-text-field
            v-model.number="quota"
            label="Days a year"
            type="number"
            min="0"
            max="365"
            step="0.5"
            :disabled="unlimited"
            style="max-width: 160px"
            v-bind="field"
          />
          <v-checkbox v-model="unlimited" label="No limit" density="compact" hide-details />
        </div>
        <div>
          <div class="text-caption text-medium-emphasis mb-1">Colour</div>
          <div class="d-flex ga-2" role="radiogroup" aria-label="Colour">
            <button
              v-for="(key, index) in SWATCH_KEYS"
              :key="key"
              type="button"
              role="radio"
              class="swatch"
              :class="{ 'swatch--active': draft.color_key === key }"
              :style="{ background: `rgb(var(--v-theme-${SWATCH_COLORS[key]}))` }"
              :aria-checked="draft.color_key === key"
              :aria-label="`Colour ${index + 1}`"
              @click="draft.color_key = key"
            />
          </div>
        </div>
        <div class="d-flex ga-6 flex-wrap">
          <v-switch v-model="draft.is_paid" label="Paid" color="primary" density="compact" hide-details inset />
          <v-switch v-model="draft.is_active" label="Active" color="primary" density="compact" hide-details inset />
        </div>
        <AppCallout v-if="error" variant="error">{{ error }}</AppCallout>
      </v-form>
      <div class="d-flex justify-end ga-2 pa-6 pt-4">
        <v-btn variant="text" @click="close">Cancel</v-btn>
        <v-btn color="primary" :loading="saving" :disabled="!valid" @click="submit">Save</v-btn>
      </div>
    </v-card>
  </v-dialog>
</template>

<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import AppCallout from '@/components/common/AppCallout.vue'
import { useLeavePolicyConfigStore } from '@/stores/leavePolicyConfig'
import type { LeaveTypeRead, LeaveTypeWrite } from '@/types/leavePolicy'
import { codeFromName, SWATCH_COLORS, SWATCH_KEYS, toNumberOrNull } from '@/utils/leave'

const props = defineProps<{ modelValue: boolean; policyId: string; type: LeaveTypeRead | null }>()
const emit = defineEmits<(e: 'update:modelValue', value: boolean) => void>()

const store = useLeavePolicyConfigStore()
const field = { variant: 'outlined', density: 'compact', hideDetails: 'auto' } as const
const draft = ref<LeaveTypeWrite>(blank())
const quota = ref<number | null>(12)
const unlimited = ref(false)
const codeTouched = ref(false)
const saving = ref(false)
const error = ref('')

const valid = computed(
  () =>
    !!draft.value.name.trim() &&
    !!draft.value.code.trim() &&
    (unlimited.value || (typeof quota.value === 'number' && quota.value >= 0 && quota.value <= 365)),
)

function blank(): LeaveTypeWrite {
  return { name: '', code: '', annual_quota_days: null, is_paid: true, color_key: SWATCH_KEYS[0], is_active: true }
}

watch(
  () => props.modelValue,
  open => {
    if (!open) return
    const type = props.type
    draft.value = type
      ? {
          name: type.name,
          code: type.code,
          annual_quota_days: type.annual_quota_days,
          is_paid: type.is_paid,
          color_key: type.color_key,
          is_active: type.is_active,
        }
      : blank()
    const current = type ? toNumberOrNull(type.annual_quota_days) : 12
    unlimited.value = !!type && current === null
    quota.value = current ?? 12
    codeTouched.value = !!type
    error.value = ''
  },
)

function syncCode(name: string): void {
  if (!codeTouched.value) draft.value.code = codeFromName(name)
}

function close(): void {
  emit('update:modelValue', false)
}

async function submit(): Promise<void> {
  if (!valid.value) return
  saving.value = true
  const body: LeaveTypeWrite = {
    ...draft.value,
    name: draft.value.name.trim(),
    code: draft.value.code.trim().toUpperCase(),
    annual_quota_days: unlimited.value ? null : quota.value,
  }
  error.value = (await store.saveType(props.policyId, body, props.type?.id ?? null)) ?? ''
  saving.value = false
  if (!error.value) close()
}
</script>

<style scoped>
.form-grid {
  display: grid;
  grid-template-columns: 2fr 1fr;
  gap: 12px;
}
.swatch {
  width: 24px;
  height: 24px;
  border-radius: 50%;
  border: 2px solid transparent;
  cursor: pointer;
}
.swatch--active {
  outline: 2px solid rgb(var(--v-theme-on-surface));
  outline-offset: 2px;
}
</style>
