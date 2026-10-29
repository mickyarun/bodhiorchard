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

<!-- Settings group at the foot of the sidebar. The pages, their order,
     labels and permission checks come from utils/settingsSections.ts, the
     same list the Integrations page shows beside its cards. -->
<template>
  <v-list-group v-if="links.length > 0" value="settings">
    <template #activator="{ props, isOpen }">
      <!-- It opens and closes the group: a button that says whether it is
           open, not a list option (so no aria-selected). -->
      <v-list-item
        v-bind="props"
        role="button"
        :aria-expanded="isOpen"
        :aria-selected="null"
        prepend-icon="mdi-cog-outline"
        title="Settings"
        rounded="lg"
      />
    </template>
    <v-list-item
      v-for="link in links"
      :key="link.to"
      :title="link.title"
      :to="link.to"
      :exact="link.to === '/settings'"
      rounded="lg"
      class="pl-10"
    />
  </v-list-group>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { useSettingsSections } from '@/composables/useSettingsSections'

const groups = useSettingsSections()
const links = computed(() => groups.value.flatMap(g => g.items))
</script>
