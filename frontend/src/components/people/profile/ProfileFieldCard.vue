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

<!-- One titled card of profile fields, with an optional Edit text button
     in its heading. -->
<template>
  <AppPanel :title="title">
    <template v-if="editable" #action>
      <v-btn variant="text" size="small" color="primary" :aria-label="`Edit ${title}`" @click="emit('edit')">
        Edit
      </v-btn>
    </template>
    <FieldGrid :fields="fields" :locked-hint="lockedHint" />
    <slot />
  </AppPanel>
</template>

<script setup lang="ts">
import AppPanel from '@/components/common/AppPanel.vue'
import FieldGrid, { type GridField } from '@/components/people/FieldGrid.vue'

defineProps<{
  title: string
  fields: GridField[]
  editable?: boolean
  lockedHint?: string
}>()

const emit = defineEmits<{ edit: [] }>()
</script>
