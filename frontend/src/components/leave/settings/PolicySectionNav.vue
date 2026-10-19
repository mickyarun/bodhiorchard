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

<!-- The sections of a policy: a sticky side list on wide screens, a row
     of chips above the content on narrow ones. -->
<template>
  <nav aria-label="Policy sections" class="section-nav">
    <v-list v-if="mdAndUp" nav density="comfortable" bg-color="transparent" class="pa-0">
      <template v-for="item in POLICY_SECTIONS" :key="item.value">
        <v-divider v-if="item.value === 'history'" class="my-2" />
        <v-list-item
          :active="section === item.value"
          :prepend-icon="item.icon"
          :title="item.title"
          :aria-current="section === item.value ? 'page' : undefined"
          color="primary"
          rounded="lg"
          @click="section = item.value"
        >
          <template v-if="item.value === 'people'" #append>
            <v-chip size="x-small" variant="tonal" label :aria-label="peopleCount(people)">{{ people }}</v-chip>
          </template>
        </v-list-item>
      </template>
    </v-list>
    <v-chip-group v-else v-model="section" mandatory selected-class="text-primary" class="mb-4">
      <v-chip v-for="item in POLICY_SECTIONS" :key="item.value" :value="item.value" :prepend-icon="item.icon" variant="outlined">
        {{ item.title }}<template v-if="item.value === 'people'">&nbsp;({{ people }})</template>
      </v-chip>
    </v-chip-group>
  </nav>
</template>

<script setup lang="ts">
import { useDisplay } from 'vuetify'
import { peopleCount, POLICY_SECTIONS, type PolicySection } from '@/utils/leavePolicyDisplay'

defineProps<{ people: number }>()
const section = defineModel<PolicySection>({ required: true })

const { mdAndUp } = useDisplay()
</script>

<style scoped>
@media (min-width: 960px) {
  .section-nav {
    position: sticky;
    top: 24px;
    align-self: start;
  }
}
</style>
