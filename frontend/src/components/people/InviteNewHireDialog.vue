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

<!-- HR invites a new hire from the People workspace: an account with a
     People-safe role and a temporary password they replace at first
     sign-in. The employee record is added next (Add employee opens with
     them picked). -->
<template>
  <v-dialog :model-value="modelValue" max-width="480" @update:model-value="emit('update:modelValue', $event)">
    <v-card color="surface" rounded="lg">
      <div class="d-flex align-center justify-space-between pa-6 pb-2">
        <h2 class="text-h6 font-weight-bold">Invite new hire</h2>
        <v-btn icon="mdi-close" variant="text" size="small" aria-label="Close" @click="close" />
      </div>
      <v-form class="px-6 d-flex flex-column ga-3" @submit.prevent="submit">
        <v-text-field v-model="name" label="Full name" maxlength="255" v-bind="FIELD" autofocus />
        <v-text-field v-model="email" label="Work email" type="email" maxlength="320" v-bind="FIELD" />
        <v-select
          v-model="roleId"
          :items="roles"
          item-value="id"
          :item-title="r => roleLabel(r.name)"
          label="Role"
          :hint="roleHint"
          persistent-hint
          v-bind="FIELD"
        />
        <v-text-field
          v-model="password"
          label="Temporary password"
          readonly
          hint="Share it with them privately. They'll choose their own at first sign-in."
          persistent-hint
          v-bind="FIELD"
        >
          <template #append-inner>
            <v-btn icon="mdi-content-copy" size="x-small" variant="text" aria-label="Copy password" @click="copy" />
            <v-btn icon="mdi-refresh" size="x-small" variant="text" aria-label="New password" @click="password = temporaryPassword()" />
          </template>
        </v-text-field>
        <AppCallout v-if="error" variant="error">{{ error }}</AppCallout>
      </v-form>
      <div class="d-flex justify-end ga-2 pa-4">
        <v-btn variant="text" @click="close">Cancel</v-btn>
        <v-btn color="primary" variant="flat" :loading="saving" :disabled="!valid" @click="submit">Invite</v-btn>
      </div>
    </v-card>
  </v-dialog>
</template>

<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import AppCallout from '@/components/common/AppCallout.vue'
import { usePermissions } from '@/composables/usePermissions'
import { useAuthStore } from '@/stores/auth'
import { useMembersStore } from '@/stores/members'
import { grantableRoles, roleLabel, temporaryPassword } from '@/utils/inviteNewHire'

const props = defineProps<{ modelValue: boolean }>()
const emit = defineEmits<{
  (e: 'update:modelValue', value: boolean): void
  (e: 'invited', userId: string): void
}>()

const FIELD = { variant: 'outlined', density: 'compact', hideDetails: 'auto' } as const
// People-only by default: a new hire outside engineering sees leave and their details.
const DEFAULT_ROLE = 'sales'

const members = useMembersStore()
const authStore = useAuthStore()
const { isOrgOwner } = usePermissions()
const name = ref('')
const email = ref('')
const roleId = ref<string | null>(null)
const password = ref('')
const saving = ref(false)
const error = ref('')

const roles = computed(() =>
  grantableRoles(members.roles, authStore.user?.permissions ?? [], isOrgOwner.value),
)
const roleHint = computed(
  () => roles.value.find(r => r.id === roleId.value)?.description ?? 'Decides what they can open.',
)
const valid = computed(
  () => !!name.value.trim() && /.+@.+\..+/.test(email.value.trim()) && !!roleId.value,
)

watch(
  () => props.modelValue,
  async open => {
    if (!open) return
    name.value = ''
    email.value = ''
    password.value = temporaryPassword()
    error.value = ''
    await members.fetchRoles()
    roleId.value = roles.value.find(r => r.name === DEFAULT_ROLE)?.id ?? null
  },
)

function close(): void {
  emit('update:modelValue', false)
}

async function copy(): Promise<void> {
  try {
    await navigator.clipboard.writeText(password.value)
  } catch {
    error.value = "Couldn't copy. Select the password and copy it by hand."
  }
}

async function submit(): Promise<void> {
  if (!valid.value || !roleId.value) return
  saving.value = true
  const created = await members.addMember({
    name: name.value.trim(),
    email: email.value.trim().toLowerCase(),
    password: password.value,
    roleId: roleId.value,
    mustChangePassword: true,
  })
  saving.value = false
  if (!created) {
    error.value = members.error ?? "Couldn't invite them."
    return
  }
  close()
  emit('invited', created.id)
}
</script>
