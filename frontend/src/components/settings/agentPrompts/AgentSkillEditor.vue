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

<!-- Expanded editor under a skill row: the field grid and the action bar.
     Reset and delete only ask; the page owns the confirm dialogs. -->
<template>
  <div class="skill-editor">
    <v-divider />

    <AgentSkillEditorFields v-model:form="form" v-model:preview-mode="previewMode" :caps="caps" />

    <!-- Action bar -->
    <div class="editor-actions">
      <v-btn
        color="primary"
        variant="flat"
        :loading="store.saving"
        class="text-none"
        @click="emit('save')"
      >
        Save changes
      </v-btn>
      <v-btn variant="text" class="text-none" @click="emit('cancel')">
        Cancel
      </v-btn>
      <v-btn
        v-if="!skill.isDefault && skill.id"
        variant="tonal"
        color="secondary"
        prepend-icon="mdi-star-outline"
        :loading="store.saving"
        class="text-none"
        @click="store.setDefault(skill.id)"
      >
        Set as default
      </v-btn>
      <v-spacer />
      <v-btn
        v-if="skill.isCustom && skill.id"
        variant="text"
        color="error"
        prepend-icon="mdi-trash-can-outline"
        :loading="store.saving"
        class="text-none"
        @click="emit('delete', skill.id)"
      >
        Delete skill
      </v-btn>
      <v-btn
        v-else-if="!skill.isCustom"
        variant="text"
        :color="skill.isCustomized ? 'warning' : 'default'"
        prepend-icon="mdi-restore"
        :loading="store.saving"
        class="text-none"
        @click="emit('reset', {
          slug: skill.skillSlug,
          agentType: skill.agentType,
          isCustomized: skill.isCustomized,
        })"
      >
        Reset to default
      </v-btn>
    </div>
  </div>
</template>

<script setup lang="ts">
import { useAgentSkillsStore, type AgentSkill } from '@/stores/agentSkills'
import AgentSkillEditorFields from './AgentSkillEditorFields.vue'
import type { SkillCaps } from './skillCapabilities.util'
import type { PreviewMode, SkillEditForm, SkillResetTarget } from './skillEditForm.util'

defineProps<{
  skill: AgentSkill
  caps: SkillCaps
}>()
const form = defineModel<SkillEditForm>('form', { required: true })
const previewMode = defineModel<PreviewMode>('previewMode', { required: true })
const emit = defineEmits<{
  save: []
  cancel: []
  delete: [id: string]
  reset: [target: SkillResetTarget]
}>()

const store = useAgentSkillsStore()
</script>

<style scoped>
.skill-editor {
  padding: 14px 18px 18px;
}

.editor-actions {
  display: flex;
  align-items: center;
  gap: 8px;
  padding-top: 14px;
  margin-top: 14px;
  border-top: 1px solid rgba(var(--v-theme-on-surface), 0.05);
}
</style>
