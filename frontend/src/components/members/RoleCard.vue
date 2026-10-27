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

<!-- One role: its name, whether it is built in, what it is for and a
     preview of its permissions. Custom roles can be edited or deleted. -->
<template>
  <article class="role-card">
    <header class="role-card__head">
      <span class="role-card__name">{{ roleTitle(role.name) }}</span>
      <AppTag>{{ isSystem ? 'Built in' : 'Custom' }}</AppTag>
    </header>
    <p v-if="role.description" class="role-card__desc">{{ role.description }}</p>
    <p v-if="role.baseRoleName && !isSystem" class="role-card__desc">Works like {{ roleTitle(role.baseRoleName) }}</p>
    <div class="role-card__perms">
      <span v-if="role.permissions.length === 0" class="role-card__none">No permissions</span>
      <span v-for="perm in preview" :key="perm.id" class="perm">{{ perm.name }}</span>
      <v-tooltip v-if="hidden.length" location="bottom" max-width="320">
        <template #activator="{ props: tip }">
          <button v-bind="tip" type="button" class="perm perm--more">+{{ hidden.length }} more</button>
        </template>
        {{ hidden.map(p => p.name).join(', ') }}
      </v-tooltip>
    </div>
    <footer v-if="!isSystem" class="role-card__actions">
      <v-btn variant="text" size="small" prepend-icon="mdi-pencil-outline" @click="emit('edit', role)">Edit</v-btn>
      <v-btn variant="text" size="small" color="error" prepend-icon="mdi-delete-outline" @click="emit('delete', role)">Delete</v-btn>
    </footer>
  </article>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import AppTag from '@/components/common/AppTag.vue'
import type { RoleOption } from '@/stores/members'
import { roleTitle } from '@/utils/members'

const PREVIEW_COUNT = 5

const props = defineProps<{ role: RoleOption }>()
const emit = defineEmits<{ edit: [RoleOption]; delete: [RoleOption] }>()

const isSystem = computed(() => props.role.scopeType === 'SYSTEM')
const preview = computed(() => props.role.permissions.slice(0, PREVIEW_COUNT))
const hidden = computed(() => props.role.permissions.slice(PREVIEW_COUNT))
</script>

<style scoped>
.role-card {
  display: flex;
  flex-direction: column;
  gap: 10px;
  min-width: 0;
  padding: 16px 18px;
  border-radius: 12px;
  border: 1px solid rgb(var(--v-theme-rule));
  background: rgb(var(--v-theme-surface));
}
.role-card__head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
}
.role-card__name {
  font-size: 15px;
  font-weight: 600;
  overflow-wrap: anywhere;
}
.role-card__desc,
.role-card__none {
  margin: 0;
  font-size: 13px;
  color: rgb(var(--v-theme-on-surface-variant));
}
.role-card__perms {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}
.perm {
  padding: 2px 8px;
  border-radius: 6px;
  font-size: 12px;
  line-height: 18px;
  font-family: var(--font-mono);
  color: rgb(var(--v-theme-ink-2));
  background: rgb(var(--v-theme-surface-variant));
  border: 0;
}
.perm--more {
  font-family: inherit;
  font-weight: 600;
  cursor: pointer;
}
.role-card__actions {
  display: flex;
  justify-content: space-between;
  margin-top: auto;
}
</style>
