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

<!-- Settings group at the foot of the sidebar. Each entry mirrors its
     route's permission so visibility tracks what the user can open. -->
<template>
  <v-list-group v-if="canViewSettings || canConfigureLeave || canManageEmployees" value="settings">
    <template #activator="{ props }">
      <v-list-item
        v-bind="props"
        prepend-icon="mdi-cog-outline"
        title="Settings"
        rounded="lg"
      />
    </template>
    <v-list-item
      v-if="canViewConnections"
      title="Integrations"
      to="/settings"
      rounded="lg"
      class="pl-10"
    />
    <v-list-item
      v-if="canViewCodeSettings"
      title="Code"
      to="/settings/code"
      rounded="lg"
      class="pl-10"
    />
    <v-list-item
      v-if="canViewDesignSystems"
      title="Design Systems"
      to="/settings/design-systems"
      rounded="lg"
      class="pl-10"
    />
    <v-list-item
      v-if="canViewAgentPrompts"
      title="Agent Prompts"
      to="/settings/agent-prompts"
      rounded="lg"
      class="pl-10"
    />
    <v-list-item
      v-if="canViewQAAutomation"
      title="QA Automation"
      to="/settings/qa-automation"
      rounded="lg"
      class="pl-10"
    />
    <v-list-item
      v-if="canViewPresenceSettings"
      title="Presence & Auto Mode"
      to="/settings/presence"
      rounded="lg"
      class="pl-10"
    />
    <v-list-item
      v-if="canViewJiraImport"
      title="Jira Import"
      to="/settings/jira-import"
      rounded="lg"
      class="pl-10"
    />
    <v-list-item
      v-if="canManageQuiz"
      title="Quiz Game"
      to="/settings/quiz-game"
      rounded="lg"
      class="pl-10"
    />
    <v-list-item
      v-if="canManageQuiz"
      title="Quiz Review"
      to="/settings/quiz-review"
      rounded="lg"
      class="pl-10"
    />
    <v-list-item
      v-if="canConfigureLeave"
      title="Leave"
      to="/settings/leave"
      rounded="lg"
      class="pl-10"
    />
    <v-list-item
      v-if="canManageEmployees"
      title="Offices"
      to="/settings/offices"
      rounded="lg"
      class="pl-10"
    />
    <!-- MCP Connect is self-service for anyone in the engineering
         workspace (mint / revoke their own tokens). -->
    <v-list-item
      v-if="canAccessEngineering"
      title="MCP Connect"
      to="/settings/mcp-connect"
      rounded="lg"
      class="pl-10"
    />
  </v-list-group>
</template>

<script setup lang="ts">
import { usePermissions } from '@/composables/usePermissions'

const {
  canAccessEngineering,
  canViewSettings,
  canViewConnections,
  canViewCodeSettings,
  canViewDesignSystems,
  canViewAgentPrompts,
  canViewQAAutomation,
  canViewPresenceSettings,
  canViewJiraImport,
  canManageQuiz,
  canConfigureLeave,
  canManageEmployees,
} = usePermissions()
</script>
