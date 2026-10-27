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

<!-- Import people from the connected GitHub organization. Everyone not
     yet added is selected on open; they all get the same starting
     password and role. -->
<template>
  <v-dialog v-model="open" max-width="600" persistent>
    <v-card>
      <v-card-title class="d-flex align-center justify-space-between">
        <span>Import from GitHub</span>
        <v-btn icon="mdi-close" variant="text" size="small" aria-label="Close" @click="open = false" />
      </v-card-title>
      <v-card-text>
        <div v-if="gh.loading.value" class="d-flex justify-center py-8">
          <v-progress-circular indeterminate color="primary" aria-label="Loading GitHub members" />
        </div>
        <AppCallout v-if="gh.error.value" variant="error" class="mb-4">{{ gh.error.value }}</AppCallout>

        <template v-if="!gh.loading.value && gh.members.value.length > 0">
          <div class="d-flex align-center justify-space-between mb-2">
            <span class="text-body-2 text-medium-emphasis">
              {{ gh.importable.value.length }} available<template v-if="gh.addedCount.value > 0">, {{ gh.addedCount.value }} already added</template>
            </span>
            <v-btn variant="text" size="small" :disabled="gh.importable.value.length === 0" @click="gh.toggleAll()">
              {{ gh.allSelected.value ? 'Deselect all' : 'Select all' }}
            </v-btn>
          </div>
          <v-list density="compact" class="gh-list mb-3">
            <v-list-item
              v-for="person in gh.members.value"
              :key="person.login"
              :disabled="person.already_added"
              @click="gh.toggle(person)"
            >
              <template #prepend>
                <v-checkbox-btn
                  :model-value="person.already_added || gh.isSelected(person.login)"
                  :disabled="person.already_added"
                  :aria-label="`Import ${person.name || person.login}`"
                  class="mr-2"
                  @click.stop
                  @update:model-value="gh.toggle(person)"
                />
                <v-avatar size="32" class="mr-3"><v-img :src="person.avatar_url" alt="" /></v-avatar>
              </template>
              <v-list-item-title>{{ person.name || person.login }}</v-list-item-title>
              <v-list-item-subtitle v-if="person.email">{{ person.email }}</v-list-item-subtitle>
              <template #append>
                <AppTag v-if="person.already_added" color="success">Added</AppTag>
              </template>
            </v-list-item>
          </v-list>
        </template>

        <p v-if="gh.loaded.value && !gh.loading.value && !gh.error.value && gh.members.value.length === 0" class="text-body-2 mb-0">
          Nobody found in the GitHub organization.
        </p>

        <div v-if="gh.selected.value.length > 0" class="mt-3">
          <div class="text-body-2 font-weight-medium mb-2">{{ plural(gh.selected.value.length, 'person', 'people') }} selected</div>
          <PasswordField
            v-model="password"
            label="Starting password for everyone imported"
            variant="outlined"
            density="compact"
            autocomplete="new-password"
            class="mb-3"
            hint="At least 6 characters. They can change it after signing in."
            persistent-hint
          />
          <v-select
            v-model="roleId"
            :items="roleItems(store.roles)"
            label="Role for everyone imported (optional)"
            variant="outlined"
            density="compact"
            clearable
          />
        </div>
      </v-card-text>
      <v-card-actions class="px-4 pb-4">
        <v-spacer />
        <v-btn variant="text" @click="open = false">Cancel</v-btn>
        <v-btn
          color="primary"
          variant="flat"
          :loading="importing"
          :disabled="gh.selected.value.length === 0 || password.length < MIN_PASSWORD"
          @click="submit"
        >
          Import {{ plural(gh.selected.value.length, 'person', 'people') }}
        </v-btn>
      </v-card-actions>
    </v-card>
  </v-dialog>
</template>

<script setup lang="ts">
import { ref, watch } from 'vue'
import AppCallout from '@/components/common/AppCallout.vue'
import AppTag from '@/components/common/AppTag.vue'
import PasswordField from '@/components/common/PasswordField.vue'
import { useGithubOrgMembers } from '@/composables/useGithubOrgMembers'
import { useMembersStore } from '@/stores/members'
import { plural } from '@/utils/format'
import { roleItems } from '@/utils/members'

const MIN_PASSWORD = 6

const open = defineModel<boolean>({ required: true })
const store = useMembersStore()
const gh = useGithubOrgMembers()

const password = ref('')
const roleId = ref<string | null>('')
const importing = ref(false)

watch(open, isOpen => {
  if (!isOpen) return
  password.value = ''
  roleId.value = store.roles.find(r => r.name.toLowerCase() === 'developer')?.id ?? ''
  void gh.load()
})

async function submit(): Promise<void> {
  importing.value = true
  let imported = 0
  for (const person of gh.selected.value) {
    const ok = await store.addMember({
      name: person.name || person.login,
      email: person.email || `${person.login}@github.placeholder`,
      password: password.value,
      avatarUrl: person.avatar_url || undefined,
      githubUsername: person.login,
      roleId: roleId.value || undefined,
    })
    if (ok) imported++
  }
  importing.value = false
  if (imported > 0) {
    open.value = false
    await store.fetchMembers()
  }
}
</script>

<style scoped>
.gh-list {
  max-height: 300px;
  overflow-y: auto;
}
</style>
