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

<!-- A member's photo or initials, name, email, GitHub handle and any
     linked email aliases (each can be unlinked). -->
<template>
  <div class="m-table__who">
    <v-avatar v-if="avatar" size="32"><v-img :src="avatar" alt="" /></v-avatar>
    <AppMonogram v-else :name="member.name" />
    <div class="who">
      <span class="m-table__name">{{ member.name }}</span>
      <span class="m-table__sub email" :title="member.email">{{ member.email }}</span>
      <span v-if="member.githubUsername" class="m-table__sub">@{{ member.githubUsername }}</span>
      <span v-if="member.emailAliases?.length" class="aliases" data-test="member-aliases">
        <v-chip
          v-for="alias in member.emailAliases"
          :key="alias"
          size="x-small"
          variant="tonal"
          closable
          close-icon="mdi-link-variant-off"
          :close-label="`Unlink alias ${alias}`"
          :data-test-alias="alias"
          @click:close="emit('unlink', alias)"
        >
          {{ alias }}
        </v-chip>
      </span>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import AppMonogram from '@/components/common/AppMonogram.vue'
import type { Member } from '@/stores/members'
import { resolveAvatarUrl } from '@/utils/avatar'

const props = defineProps<{ member: Member }>()
const emit = defineEmits<{ unlink: [string] }>()

const avatar = computed(() => resolveAvatarUrl(props.member.avatarUrl))
</script>

<style scoped src="./membersTable.css"></style>
<style scoped>
.who {
  display: flex;
  flex-direction: column;
  min-width: 0;
}
/* Long emails end in an ellipsis (full address on hover) instead of
   breaking mid-word. */
.email {
  display: block;
  max-width: 280px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  overflow-wrap: normal;
}
@media (max-width: 600px) {
  .email {
    max-width: 120px;
  }
}
.aliases {
  display: flex;
  flex-wrap: wrap;
  gap: 4px;
  margin-top: 4px;
}
</style>
