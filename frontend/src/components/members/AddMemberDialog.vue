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

<!-- Add one person by hand: name, email, a starting password and an
     optional role. -->
<template>
  <v-dialog v-model="open" max-width="480" persistent>
    <v-card>
      <v-card-title class="d-flex align-center justify-space-between">
        <span>Add member</span>
        <v-btn icon="mdi-close" variant="text" size="small" aria-label="Close" @click="open = false" />
      </v-card-title>
      <v-card-text>
        <v-text-field v-model="form.name" label="Name" variant="outlined" density="compact" class="mb-3" :rules="[required('Name')]" />
        <v-text-field
          v-model="form.email"
          label="Email"
          type="email"
          variant="outlined"
          density="compact"
          class="mb-3"
          :rules="[required('Email')]"
        />
        <PasswordField
          v-model="form.password"
          label="Starting password"
          variant="outlined"
          density="compact"
          class="mb-3"
          autocomplete="new-password"
          hint="At least 6 characters. They change it after signing in."
          persistent-hint
        />
        <v-select
          v-model="form.roleId"
          :items="roleItems(store.roles)"
          label="Role (optional)"
          variant="outlined"
          density="compact"
          clearable
        />
      </v-card-text>
      <v-card-actions class="px-4 pb-4">
        <v-spacer />
        <v-btn variant="text" @click="open = false">Cancel</v-btn>
        <v-btn color="primary" variant="flat" :loading="saving" :disabled="!canSubmit" @click="submit">Add member</v-btn>
      </v-card-actions>
    </v-card>
  </v-dialog>
</template>

<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import PasswordField from '@/components/common/PasswordField.vue'
import { useMembersStore } from '@/stores/members'
import { roleItems } from '@/utils/members'

const MIN_PASSWORD = 6

const open = defineModel<boolean>({ required: true })
const store = useMembersStore()

const saving = ref(false)
const form = ref({ name: '', email: '', password: '', roleId: '' as string | null })

watch(open, isOpen => {
  if (isOpen) form.value = { name: '', email: '', password: '', roleId: '' }
})

const canSubmit = computed(
  () => !!form.value.name.trim() && !!form.value.email.trim() && form.value.password.length >= MIN_PASSWORD,
)

function required(label: string) {
  return (v: string) => !!v || `${label} is required`
}

async function submit(): Promise<void> {
  saving.value = true
  const ok = await store.addMember({
    name: form.value.name,
    email: form.value.email,
    password: form.value.password,
    roleId: form.value.roleId || undefined,
  })
  saving.value = false
  if (ok) open.value = false
}
</script>
