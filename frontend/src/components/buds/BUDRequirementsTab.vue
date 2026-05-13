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
import { computed } from 'vue'
import type { BUDDocument } from '@/types'
import { renderMarkdown } from '@/utils/markdown'
import BUDLinkedFeaturesPanel from './BUDLinkedFeaturesPanel.vue'

const props = defineProps<{
  bud: BUDDocument
  editing: boolean
  editValue: string
  agentLocked: boolean
}>()

const emit = defineEmits<{
  'update:editValue': [value: string]
  save: []
  startEdit: []
  enrich: []
  'features-changed': []
}>()

const isJiraImported = computed(() => props.bud.metadata?.source === 'jira_import')

const showEnrichHint = computed(() =>
  isJiraImported.value
  && !props.agentLocked
  && (props.bud.requirements_md?.length ?? 0) < 200,
)
</script>

<template>
  <div class="bud-requirements-tab">
    <BUDLinkedFeaturesPanel
      v-if="bud.id"
      :bud-id="bud.id"
      class="mx-4 mt-3 mb-3"
      @change="emit('features-changed')"
    />
    <textarea
      v-if="editing"
      :value="editValue"
      class="section-editor"
      placeholder="Write requirements in markdown..."
      @input="emit('update:editValue', ($event.target as HTMLTextAreaElement).value)"
      @blur="emit('save')"
    />
    <template v-else-if="bud.requirements_md">
      <v-alert
        v-if="showEnrichHint"
        type="info"
        variant="tonal"
        density="compact"
        class="mx-4 mt-3 mb-0"
      >
        <div class="d-flex align-center ga-3">
          <div class="text-caption flex-grow-1">
            Imported from Jira — use AI to expand into a full PRD with acceptance criteria
          </div>
          <v-btn size="small" variant="flat" color="primary" @click="emit('enrich')">
            <v-icon start size="15">mdi-creation-outline</v-icon>
            Enrich
          </v-btn>
        </div>
      </v-alert>
      <div class="rendered-markdown" v-html="renderMarkdown(bud.requirements_md)" />
    </template>
    <div v-else class="section-empty">
      <v-icon icon="mdi-text-box-outline" size="40" class="mb-3" />
      <div>No requirements written yet</div>
      <div class="d-flex ga-2 mt-3">
        <v-btn variant="tonal" size="small" @click="emit('startEdit')">
          <v-icon start size="15">mdi-pencil-outline</v-icon>
          Start writing
        </v-btn>
        <v-btn
          v-if="!agentLocked"
          variant="tonal"
          size="small"
          color="primary"
          @click="emit('enrich')"
        >
          <v-icon start size="15">mdi-creation-outline</v-icon>
          Enrich with AI
        </v-btn>
      </div>
    </div>
  </div>
</template>

<style src="./bud-section.css"></style>
