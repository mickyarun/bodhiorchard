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
  <v-dialog
    :model-value="modelValue"
    max-width="640"
    persistent
    scrollable
    @update:model-value="emit('update:modelValue', $event)"
  >
    <v-card class="dialog-card">
      <CustomSkillDialogHeader @close="close" />

      <v-divider />

      <!-- Body -->
      <div class="dialog-body">
        <AppCallout v-if="errorMessage" variant="error" class="mb-3">
          {{ errorMessage }}
        </AppCallout>

        <CustomSkillImportBar @loaded="onFileLoaded" @failed="errorMessage = $event" />
        <v-snackbar
          v-model="showImportToast"
          :timeout="3500"
          location="top right"
          color="primary"
          variant="elevated"
        >
          {{ importToast }}
        </v-snackbar>

        <CustomSkillFormFields v-model:form="form" @prompt-paste="onPromptPaste" />
      </div>

      <v-divider />

      <!-- Footer -->
      <footer class="dialog-footer">
        <v-spacer />
        <v-btn variant="text" class="text-none" @click="close">
          Cancel
        </v-btn>
        <v-btn
          color="primary"
          variant="flat"
          class="text-none"
          :loading="store.saving"
          :disabled="!canSubmit(form)"
          @click="submit"
        >
          Create skill
        </v-btn>
      </footer>
    </v-card>
  </v-dialog>
</template>

<script setup lang="ts">
import AppCallout from '@/components/common/AppCallout.vue'
import { ref, watch } from 'vue'
import { type AgentType, useAgentSkillsStore } from '@/stores/agentSkills'
import CustomSkillDialogHeader from '@/components/settings/customSkill/CustomSkillDialogHeader.vue'
import CustomSkillFormFields from '@/components/settings/customSkill/CustomSkillFormFields.vue'
import CustomSkillImportBar from '@/components/settings/customSkill/CustomSkillImportBar.vue'
import {
  canSubmit,
  templateForAgent,
  type CustomSkillForm,
} from '@/components/settings/customSkill/customSkillForm.util'
import { useCustomSkillImport } from '@/composables/useCustomSkillImport'

const props = defineProps<{
  modelValue: boolean
  initialAgentType?: AgentType | null
}>()
const emit = defineEmits<{
  'update:modelValue': [value: boolean]
  created: []
}>()

const store = useAgentSkillsStore()
const errorMessage = ref<string | null>(null)
const form = ref<CustomSkillForm>(templateForAgent(store.skills, props.initialAgentType ?? 'bud'))
const { showImportToast, importToast, onFileLoaded, onPromptPaste } = useCustomSkillImport(form)

watch(
  () => props.modelValue,
  open => {
    if (open) {
      form.value = templateForAgent(store.skills, props.initialAgentType ?? 'bud')
      errorMessage.value = null
    }
  },
)

// Re-fill the template when the user switches agent type while the
// dialog is open — keeps prompt/tools/etc. in sync with whichever
// agent's defaults they're now starting from.
watch(
  () => form.value.agentType,
  (newAt, oldAt) => {
    if (!props.modelValue) return
    if (newAt === oldAt) return
    form.value = templateForAgent(store.skills, newAt)
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
.dialog-card {
  display: flex;
  flex-direction: column;
  max-height: 90vh;
  background: rgb(var(--v-theme-surface));
  border-radius: 14px;
  overflow: hidden;
}

/* ── Body ─────────────────────────────────────────────────── */

.dialog-body {
  padding: 16px 18px;
  overflow-y: auto;
  flex: 1;
}

/* Shrink Vuetify's default outlined-field min-height to match label-above
   convention. Density 'compact' already lowers it; this nudges harder for
   selects whose item slot bumps the height back up. */
:deep(.v-field--variant-outlined.v-field--density-compact) {
  --v-field-padding-top: 0;
}
:deep(.v-field--variant-outlined .v-field__input) {
  min-height: 38px;
  padding-top: 4px;
  padding-bottom: 4px;
}

/* ── Footer ───────────────────────────────────────────────── */

.dialog-footer {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 12px 16px;
  flex-shrink: 0;
}
</style>
