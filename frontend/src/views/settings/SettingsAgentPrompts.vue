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
  <div class="settings-page">
    <AgentPromptsHeader
      v-model:search="search"
      v-model:filter-mode="filterMode"
      @create="showCreateDialog = true"
    />

    <!-- Content -->
    <div class="page-content px-6 pb-8">
      <div v-if="store.loading" class="d-flex justify-center py-16">
        <v-progress-circular indeterminate color="primary" />
      </div>

      <div v-else-if="store.skills.length === 0" class="empty-state">
        <v-icon icon="mdi-robot-confused-outline" size="48" />
        <div class="empty-title">No agent skills yet</div>
        <div class="empty-sub">
          Skills will appear here once they're seeded from your project.
        </div>
      </div>

      <div v-else-if="filteredGroups.length === 0" class="empty-state">
        <v-icon icon="mdi-filter-remove-outline" size="48" />
        <div class="empty-title">No matches</div>
        <div class="empty-sub">Try a different search or filter.</div>
      </div>

      <!-- Agent-type groups -->
      <div v-else class="d-flex flex-column ga-5">
        <AgentSkillGroup
          v-for="group in filteredGroups"
          :key="group.agentType"
          :agent-type="group.agentType"
          :count="group.skills.length"
          @add="openCreateForAgent(group.agentType)"
        >
          <article
            v-for="skill in group.skills"
            :key="skillKey(skill)"
            class="skill-row"
            :class="{ 'is-open': isOpen(skill) }"
          >
            <AgentSkillSummary :skill="skill" :open="isOpen(skill)" :caps="caps" @toggle="toggle(skill)" />
            <AgentSkillEditor
              v-if="isOpen(skill)"
              v-model:form="editForm"
              v-model:preview-mode="previewMode"
              :skill="skill"
              :caps="caps"
              @save="saveSkill(skill)"
              @cancel="collapse"
              @delete="confirmDeleteId = $event"
              @reset="confirmResetTarget = $event"
            />
          </article>
        </AgentSkillGroup>
      </div>
    </div>

    <!-- Reset confirmation -->
    <AgentSkillConfirmDialog
      v-model="showResetDialog"
      icon="mdi-restore"
      tone="warning"
      title="Reset to default?"
      confirm-label="Reset"
      :loading="store.saving"
      @confirm="doReset"
    >
      <template v-if="confirmResetTarget?.isCustomized">
        Discards your customizations for
        <strong>{{ confirmResetTarget?.slug }}</strong>
        and restores the original prompt. Can't be undone.
      </template>
      <template v-else>
        Reloads
        <strong>{{ confirmResetTarget?.slug }}</strong>
        from its canonical skill file on disk. Use this after the
        prompt has been updated in source. No customizations to lose.
      </template>
    </AgentSkillConfirmDialog>

    <!-- Delete confirmation -->
    <AgentSkillConfirmDialog
      v-model="showDeleteDialog"
      icon="mdi-trash-can-outline"
      tone="error"
      title="Delete this custom skill?"
      confirm-label="Delete"
      :loading="store.saving"
      @confirm="doDelete"
    >
      Permanently removes the skill. BUDs that pinned it will fall
      back to the agent default.
    </AgentSkillConfirmDialog>

    <CustomSkillDialog
      v-model="showCreateDialog"
      :initial-agent-type="createForAgent"
      @created="onCustomCreated"
    />
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { useAgentSkillsStore, type AgentType } from '@/stores/agentSkills'
import AgentPromptsHeader from '@/components/settings/agentPrompts/AgentPromptsHeader.vue'
import AgentSkillConfirmDialog from '@/components/settings/agentPrompts/AgentSkillConfirmDialog.vue'
import AgentSkillEditor from '@/components/settings/agentPrompts/AgentSkillEditor.vue'
import AgentSkillGroup from '@/components/settings/agentPrompts/AgentSkillGroup.vue'
import AgentSkillSummary from '@/components/settings/agentPrompts/AgentSkillSummary.vue'
import {
  groupAgentSkills,
  skillKey,
  type SkillFilterMode,
} from '@/components/settings/agentPrompts/agentPrompts.util'
import { useAgentSkillCapabilities } from '@/composables/useAgentSkillCapabilities'
import { useAgentSkillConfirm } from '@/composables/useAgentSkillConfirm'
import { useAgentSkillEditor } from '@/composables/useAgentSkillEditor'
import CustomSkillDialog from './CustomSkillDialog.vue'

const store = useAgentSkillsStore()
const { caps, load: loadProviderCapabilities } = useAgentSkillCapabilities()
const { previewMode, editForm, isOpen, toggle, collapse, saveSkill } = useAgentSkillEditor(caps)

const {
  confirmResetTarget, confirmDeleteId, showResetDialog, showDeleteDialog, doReset, doDelete,
} = useAgentSkillConfirm(collapse)
const showCreateDialog = ref(false)
const createForAgent = ref<AgentType | null>(null)
const search = ref('')
const filterMode = ref<SkillFilterMode>('all')

const filteredGroups = computed(() => groupAgentSkills(store.skills, filterMode.value, search.value))

function openCreateForAgent(at: AgentType): void {
  createForAgent.value = at
  showCreateDialog.value = true
}

function onCustomCreated(): void {
  showCreateDialog.value = false
  createForAgent.value = null
}

onMounted(() => {
  store.fetchSkills()
  loadProviderCapabilities()
})
</script>

<style scoped>
.settings-page {
  height: 100%;
  display: flex;
  flex-direction: column;
}

/* ── Content ─────────────────────────────────────────────────── */

.page-content {
  flex: 1;
  min-height: 0;
}

.empty-state {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 8px;
  padding: 72px 0;
  color: rgba(var(--v-theme-on-surface), 0.5);
}
.empty-state .v-icon { opacity: 0.4; margin-bottom: 4px; }
.empty-title { font-size: 15px; font-weight: 500; color: rgba(var(--v-theme-on-surface), 0.7); }
.empty-sub { font-size: 13px; }

/* ── Skill rows (rendered into each AgentSkillGroup) ─────────── */

.skill-row + .skill-row .skill-summary {
  border-top: 1px solid rgba(var(--v-theme-on-surface), 0.06);
}

.skill-row.is-open {
  background: rgba(var(--v-theme-on-surface), 0.025);
}
</style>
