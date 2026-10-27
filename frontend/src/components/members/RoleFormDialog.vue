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

<!-- Create or edit a custom role: name, description, the system role it
     inherits phase ownership from, and its permissions by category.
     Saving needs a name and at least one permission, as the API does. -->
<template>
  <v-dialog v-model="open" max-width="600" persistent>
    <v-card>
      <v-card-title class="d-flex align-center justify-space-between">
        <span>{{ role ? 'Edit role' : 'Create role' }}</span>
        <v-btn icon="mdi-close" variant="text" size="small" aria-label="Close" @click="open = false" />
      </v-card-title>
      <v-card-text>
        <!-- The page callout sits behind the dialog, so failures show here. -->
        <AppCallout v-if="submitError" variant="error" class="mb-3">{{ submitError }}</AppCallout>
        <v-text-field v-model="form.name" label="Role name" variant="outlined" density="compact" class="mb-3" :rules="[v => !!v || 'Name is required']" />
        <v-text-field v-model="form.description" label="Description (optional)" variant="outlined" density="compact" class="mb-3" />
        <v-select
          v-if="!isSystem"
          v-model="form.baseRoleId"
          :items="baseRoleItems(store.roles)"
          label="Base role (for auto-assignment)"
          variant="outlined"
          density="compact"
          class="mb-4"
          hint="Members with this role take part in the stages the base role owns."
          persistent-hint
          :rules="[v => !!v || 'Base role is required']"
        />
        <div class="d-flex align-center justify-space-between mb-2">
          <span class="text-subtitle-2">Permissions</span>
          <span class="text-caption" :class="form.permissionIds.length === 0 ? 'text-error' : 'text-medium-emphasis'">
            {{ form.permissionIds.length }} selected
          </span>
        </div>
        <v-expansion-panels variant="accordion" multiple>
          <v-expansion-panel v-for="cat in store.permissionCategories" :key="cat.key">
            <v-expansion-panel-title class="text-body-2 font-weight-medium py-2">
              {{ cat.name }}
              <span v-if="countSelected(cat) > 0" class="perm-count">{{ countSelected(cat) }}/{{ cat.permissions.length }}</span>
            </v-expansion-panel-title>
            <v-expansion-panel-text>
              <p v-if="cat.description" class="text-caption text-medium-emphasis mb-2">{{ cat.description }}</p>
              <div class="d-flex flex-wrap">
                <v-checkbox
                  v-for="perm in cat.permissions"
                  :key="perm.id"
                  v-model="form.permissionIds"
                  :value="perm.id"
                  :label="perm.name"
                  density="compact"
                  hide-details
                  class="mr-4"
                />
              </div>
            </v-expansion-panel-text>
          </v-expansion-panel>
        </v-expansion-panels>
      </v-card-text>
      <v-card-actions class="px-4 pb-4">
        <v-spacer />
        <v-btn variant="text" @click="open = false">Cancel</v-btn>
        <v-btn color="primary" variant="flat" :loading="saving" :disabled="!canSubmit" @click="submit">
          {{ role ? 'Save' : 'Create' }}
        </v-btn>
      </v-card-actions>
    </v-card>
  </v-dialog>
</template>

<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import AppCallout from '@/components/common/AppCallout.vue'
import { useMembersStore, type PermissionCategory, type RoleOption } from '@/stores/members'
import { baseRoleItems } from '@/utils/members'

const props = defineProps<{ role: RoleOption | null }>()
const open = defineModel<boolean>({ required: true })
const store = useMembersStore()

const saving = ref(false)
const submitError = ref('')
const form = ref({ name: '', description: '', baseRoleId: '', permissionIds: [] as string[] })

const isSystem = computed(() => props.role?.scopeType === 'SYSTEM')
const canSubmit = computed(() => !!form.value.name.trim() && form.value.permissionIds.length > 0)

// New roles start from the Developer system role so the picker is never empty.
function defaultBaseRoleId(): string {
  return store.roles.find(r => r.scopeType === 'SYSTEM' && r.name === 'developer')?.id ?? ''
}

watch(open, isOpen => {
  if (!isOpen) return
  const role = props.role
  form.value = {
    name: role?.name ?? '',
    description: role?.description ?? '',
    baseRoleId: role ? (role.baseRoleId ?? '') : defaultBaseRoleId(),
    permissionIds: role?.permissions.map(p => p.id) ?? [],
  }
  submitError.value = ''
  if (store.permissionCategories.length === 0) void store.fetchPermissions()
})

function countSelected(cat: PermissionCategory): number {
  return cat.permissions.filter(p => form.value.permissionIds.includes(p.id)).length
}

async function submit(): Promise<void> {
  saving.value = true
  submitError.value = ''
  const body = {
    name: form.value.name,
    description: form.value.description || undefined,
    permission_ids: form.value.permissionIds,
  }
  const ok = props.role
    ? await store.updateRole(props.role.id, {
        ...body,
        // A system role is its own base; only custom roles send one.
        base_role_id: isSystem.value ? undefined : form.value.baseRoleId,
      })
    : await store.createRole({ ...body, base_role_id: form.value.baseRoleId })
  saving.value = false
  if (ok) open.value = false
  else submitError.value = store.error ?? 'Could not save the role.'
}
</script>

<style scoped>
.perm-count {
  margin-left: 8px;
  font-size: 12px;
  font-weight: 600;
  color: var(--color-accent-text);
}
</style>
