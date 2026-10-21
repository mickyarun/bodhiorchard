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

<!-- Fix someone's name (HR) or your own. It's the account's name, so it
     changes everywhere they appear: leave, approvals, reports, Slack. -->
<template>
  <v-dialog :model-value="modelValue" max-width="440" @update:model-value="emit('update:modelValue', $event)">
    <v-card color="surface" rounded="lg">
      <v-card-title class="pt-5 px-6">{{ isOwn ? 'Edit your name' : 'Edit name' }}</v-card-title>
      <v-card-text class="px-6">
        <v-form @submit.prevent="submit">
          <v-text-field
            v-model="name"
            label="Full name"
            maxlength="100"
            variant="outlined"
            density="comfortable"
            hint="Shown on leave, approvals, reports and Slack."
            persistent-hint
            autofocus
          />
        </v-form>
        <AppCallout v-if="error" variant="error" class="mt-3">{{ error }}</AppCallout>
      </v-card-text>
      <v-card-actions class="px-6 pb-4">
        <v-spacer />
        <v-btn variant="text" @click="emit('update:modelValue', false)">Cancel</v-btn>
        <v-btn color="primary" variant="flat" :loading="saving" :disabled="!name.trim()" @click="submit">Save</v-btn>
      </v-card-actions>
    </v-card>
  </v-dialog>
</template>

<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import AppCallout from '@/components/common/AppCallout.vue'
import { useAuthStore } from '@/stores/auth'
import { useEmployeesStore } from '@/stores/employees'

const props = defineProps<{ modelValue: boolean; userId: string; current: string }>()
const emit = defineEmits<(e: 'update:modelValue', value: boolean) => void>()

const store = useEmployeesStore()
const authStore = useAuthStore()
const name = ref('')
const saving = ref(false)
const error = ref('')
const isOwn = computed(() => props.userId === authStore.user?.id)

watch(
  () => props.modelValue,
  open => {
    if (!open) return
    name.value = props.current
    error.value = ''
  },
)

async function submit(): Promise<void> {
  if (!name.value.trim()) return
  saving.value = true
  error.value = (await store.updateName(props.userId, name.value)) ?? ''
  saving.value = false
  if (error.value) return
  // The sidebar shows the signed-in user's name: keep it in step.
  if (isOwn.value && authStore.user && store.record) authStore.user.name = store.record.name
  emit('update:modelValue', false)
}
</script>
