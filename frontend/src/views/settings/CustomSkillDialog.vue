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

<template>
  <v-dialog :model-value="modelValue" max-width="640" persistent>
    <v-card>
      <v-card-title class="d-flex align-center pa-4">
        <v-icon icon="mdi-robot-outline" class="mr-2" />
        Add Custom Skill
        <v-spacer />
        <v-btn icon="mdi-close" variant="text" size="small" @click="close" />
      </v-card-title>
      <v-divider />
      <v-card-text class="pa-4">
        <v-alert v-if="errorMessage" type="error" variant="tonal" class="mb-3" density="compact">
          {{ errorMessage }}
        </v-alert>
        <div class="d-flex ga-3 mb-3">
          <v-select
            v-model="form.agentType"
            :items="agentTypeItems"
            item-title="title"
            item-value="value"
            label="Agent type"
            variant="outlined"
            density="compact"
            hide-details
            class="flex-grow-1"
          />
          <v-text-field
            v-model="form.skillSlug"
            label="Slug (kebab-case)"
            placeholder="my-pm"
            variant="outlined"
            density="compact"
            hide-details
            class="flex-grow-1"
          />
        </div>
        <v-text-field
          v-model="form.name"
          label="Display name"
          variant="outlined"
          density="compact"
          hide-details
          class="mb-3"
        />
        <v-text-field
          v-model="form.description"
          label="Description (one-liner)"
          variant="outlined"
          density="compact"
          hide-details
          class="mb-3"
        />
        <v-textarea
          v-model="form.prompt"
          label="Prompt (markdown)"
          variant="outlined"
          density="compact"
          hide-details
          rows="10"
          auto-grow
          class="prompt-textarea mb-3"
        />
        <div class="d-flex ga-3 mb-3">
          <v-combobox
            v-model="form.tools"
            label="Tools"
            variant="outlined"
            density="compact"
            hide-details
            multiple
            chips
            closable-chips
            class="flex-grow-1"
          />
          <v-combobox
            v-model="form.mcpTools"
            label="MCP Tools"
            variant="outlined"
            density="compact"
            hide-details
            multiple
            chips
            closable-chips
            class="flex-grow-1"
          />
        </div>
        <div class="d-flex ga-3">
          <v-select
            v-model="form.model"
            :items="modelOptions"
            item-title="title"
            item-value="value"
            label="Model"
            variant="outlined"
            density="compact"
            hide-details
            class="flex-grow-1"
          />
          <v-text-field
            v-model.number="form.maxTurns"
            type="number"
            :min="0"
            :max="100"
            label="Max turns"
            hint="0 = unlimited"
            persistent-hint
            variant="outlined"
            density="compact"
            class="flex-grow-1"
          />
        </div>
      </v-card-text>
      <v-divider />
      <v-card-actions class="pa-4">
        <v-spacer />
        <v-btn variant="text" @click="close">Cancel</v-btn>
        <v-btn
          color="primary"
          variant="flat"
          :loading="store.saving"
          :disabled="!canSubmit"
          @click="submit"
        >
          Create skill
        </v-btn>
      </v-card-actions>
    </v-card>
  </v-dialog>
</template>

<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import {
  AGENT_TYPE_LABELS,
  type AgentType,
  useAgentSkillsStore,
} from '@/stores/agentSkills'

const props = defineProps<{ modelValue: boolean }>()
const emit = defineEmits<{
  'update:modelValue': [value: boolean]
  created: []
}>()

const store = useAgentSkillsStore()
const errorMessage = ref<string | null>(null)

interface FormState {
  agentType: AgentType
  skillSlug: string
  name: string
  description: string
  prompt: string
  tools: string[]
  mcpTools: string[]
  model: string
  maxTurns: number
}

function emptyForm(): FormState {
  return {
    agentType: 'bud',
    skillSlug: '',
    name: '',
    description: '',
    prompt: '',
    tools: [],
    mcpTools: [],
    model: '',
    maxTurns: 0,
  }
}

const form = ref<FormState>(emptyForm())

const agentTypeItems = computed(() =>
  (Object.keys(AGENT_TYPE_LABELS) as AgentType[]).map(value => ({
    value,
    title: AGENT_TYPE_LABELS[value],
  })),
)

const modelOptions = [
  { title: 'Default', value: '' },
  { title: 'Sonnet', value: 'sonnet' },
  { title: 'Opus', value: 'opus' },
  { title: 'Haiku', value: 'haiku' },
]

const SLUG_REGEX = /^[a-z0-9][a-z0-9-]*$/

const canSubmit = computed(
  () =>
    form.value.name.trim().length > 0 &&
    form.value.prompt.trim().length > 0 &&
    SLUG_REGEX.test(form.value.skillSlug),
)

watch(
  () => props.modelValue,
  open => {
    if (open) {
      form.value = emptyForm()
      errorMessage.value = null
    }
  },
)

function close(): void {
  emit('update:modelValue', false)
}

async function submit(): Promise<void> {
  errorMessage.value = null
  const created = await store.createCustomSkill({
    skillSlug: form.value.skillSlug,
    agentType: form.value.agentType,
    name: form.value.name.trim(),
    description: form.value.description.trim(),
    prompt: form.value.prompt,
    tools: form.value.tools,
    mcpTools: form.value.mcpTools,
    model: form.value.model,
    maxTurns: form.value.maxTurns,
  })
  if (created) {
    emit('created')
    close()
  } else {
    errorMessage.value = store.error ?? 'Failed to create custom skill.'
  }
}
</script>

<style scoped>
.prompt-textarea :deep(textarea) {
  font-family: 'JetBrains Mono', 'Fira Code', 'Cascadia Code', monospace;
  font-size: 13px;
  line-height: 1.6;
}
</style>
