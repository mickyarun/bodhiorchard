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
  <div class="mb-6">
    <v-row>
      <!-- Claude Code (active provider) -->
      <v-col cols="12" md="6">
        <SettingsClaudeCode />
      </v-col>

      <!-- Coming Soon providers — stacked dashed cards to match the Git
           Providers / Messaging sections on this page. -->
      <v-col cols="12" md="6">
        <div class="d-flex flex-column ga-3 h-100">
          <v-card class="pa-4 coming-soon-card flex-grow-1" color="surface" variant="outlined">
            <div class="d-flex align-center ga-3">
              <v-avatar size="36" rounded="lg" class="coming-soon-avatar">
                <v-icon icon="mdi-cloud-outline" size="20" />
              </v-avatar>
              <div class="flex-grow-1">
                <div class="text-body-2 font-weight-medium">Cloud API</div>
                <div class="text-caption text-medium-emphasis">Direct Anthropic / OpenAI / Gemini</div>
              </div>
              <v-chip size="x-small" variant="tonal" color="grey">Soon</v-chip>
            </div>
          </v-card>
          <v-card class="pa-4 coming-soon-card flex-grow-1" color="surface" variant="outlined">
            <div class="d-flex align-center ga-3">
              <v-avatar size="36" rounded="lg" class="coming-soon-avatar">
                <v-icon icon="mdi-server-outline" size="20" />
              </v-avatar>
              <div class="flex-grow-1">
                <div class="text-body-2 font-weight-medium">Ollama</div>
                <div class="text-caption text-medium-emphasis">Local models via Ollama runtime</div>
              </div>
              <v-chip size="x-small" variant="tonal" color="grey">Soon</v-chip>
            </div>
          </v-card>
          <v-card class="pa-4 coming-soon-card flex-grow-1" color="surface" variant="outlined">
            <div class="d-flex align-center ga-3">
              <v-avatar size="36" rounded="lg" class="coming-soon-avatar">
                <v-icon icon="mdi-code-braces" size="20" />
              </v-avatar>
              <div class="flex-grow-1">
                <div class="text-body-2 font-weight-medium">Codex</div>
                <div class="text-caption text-medium-emphasis">OpenAI Codex CLI integration</div>
              </div>
              <v-chip size="x-small" variant="tonal" color="grey">Soon</v-chip>
            </div>
          </v-card>
        </div>
      </v-col>
    </v-row>

    <!-- Per-org merge model override (Phase 3.5) -->
    <SettingsMergeModel />
  </div>
</template>

<script setup lang="ts">
import SettingsClaudeCode from './SettingsClaudeCode.vue'
import SettingsMergeModel from './SettingsMergeModel.vue'
</script>
