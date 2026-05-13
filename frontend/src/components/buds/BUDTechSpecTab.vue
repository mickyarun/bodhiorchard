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

<script setup lang="ts">
import type { BUDDocument } from '@/types'
import { renderMarkdown } from '@/utils/markdown'
import './bud-section.css'

defineProps<{
  bud: BUDDocument
  editing: boolean
  editValue: string
}>()

const emit = defineEmits<{
  'update:editValue': [value: string]
  save: []
  startEdit: []
}>()
</script>

<template>
  <div class="bud-tech-spec-tab">
    <textarea
      v-if="editing"
      :value="editValue"
      class="section-editor"
      placeholder="Technical implementation details..."
      @input="emit('update:editValue', ($event.target as HTMLTextAreaElement).value)"
      @blur="emit('save')"
    />
    <div
      v-else-if="bud.tech_spec_md"
      class="rendered-markdown"
      v-html="renderMarkdown(bud.tech_spec_md)"
    />
    <div v-else class="section-empty">
      <v-icon icon="mdi-code-braces" size="40" class="mb-3" />
      <div>No tech spec yet</div>
      <v-btn variant="tonal" size="small" class="mt-3" @click="emit('startEdit')">
        <v-icon start size="15">mdi-pencil-outline</v-icon>
        Start writing
      </v-btn>
    </div>
  </div>
</template>
