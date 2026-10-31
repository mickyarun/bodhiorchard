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

<!-- Searchable member picker for a BUD's assignee. The activator comes
     from the slot so the header and the Details panel can each open it
     from their own control.

     It reads the member directory, which any signed-in member may list,
     rather than the admin-only members list: roles that can assign a BUD
     (a PM, say) don't hold team:manage, and the admin list would 403. -->
<template>
  <v-menu v-model="open" location="bottom start" :close-on-content-click="false">
    <template #activator="{ props: activatorProps }">
      <slot name="activator" :props="activatorProps" />
    </template>
    <v-card min-width="280" max-width="340" class="assignee-menu">
      <v-text-field
        v-model="search"
        label="Search members"
        variant="outlined"
        density="compact"
        hide-details
        prepend-inner-icon="mdi-magnify"
        autofocus
      />
      <v-list max-height="280" density="compact" class="mt-2" role="listbox" aria-label="Members">
        <v-list-item v-if="assigneeId" role="option" :aria-selected="false" @click="pick(null)">
          <template #prepend><v-icon size="20" color="error">mdi-account-remove-outline</v-icon></template>
          <v-list-item-title>Unassign</v-list-item-title>
        </v-list-item>
        <v-list-item
          v-for="m in matches"
          :key="m.id"
          role="option"
          :active="assigneeId === m.id"
          :aria-selected="assigneeId === m.id"
          @click="pick(m.id)"
        >
          <template #prepend>
            <AppMonogram class="assignee-menu__avatar" :name="m.name" :src="m.avatar_url" :size="28" />
          </template>
          <v-list-item-title>{{ m.name }}</v-list-item-title>
          <v-list-item-subtitle>{{ m.email }}</v-list-item-subtitle>
        </v-list-item>
      </v-list>
    </v-card>
  </v-menu>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useMemberDirectory } from '@/composables/useMemberDirectory'
import AppMonogram from '@/components/common/AppMonogram.vue'

defineProps<{ assigneeId: string | null }>()
const emit = defineEmits<{ change: [memberId: string | null] }>()

const { entries, ensureLoaded } = useMemberDirectory()
onMounted(() => void ensureLoaded())

const open = ref(false)
const search = ref('')
const matches = computed(() => {
  const q = (search.value ?? '').toLowerCase()
  return entries.value.filter(m => m.name.toLowerCase().includes(q))
})

function pick(memberId: string | null): void {
  emit('change', memberId)
  open.value = false
}
</script>

<style scoped>
.assignee-menu {
  padding: 8px;
}
.assignee-menu__avatar {
  margin-right: 10px;
}
</style>
