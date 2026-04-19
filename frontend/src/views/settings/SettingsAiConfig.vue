<template>
  <div>
    <!-- Claude Code connection -->
    <SettingsClaudeCode class="mb-4" />

    <!-- Coming Soon options -->
    <div>
      <div class="text-caption text-medium-emphasis mb-2 ml-1">More AI engines coming soon</div>
      <div class="d-flex flex-wrap ga-2">
        <v-chip variant="outlined" color="grey" prepend-icon="mdi-cloud-outline" disabled>
          Cloud API
          <template #append>
            <v-chip size="x-small" variant="tonal" color="grey" class="ml-1">Soon</v-chip>
          </template>
        </v-chip>
        <v-chip variant="outlined" color="grey" prepend-icon="mdi-server-outline" disabled>
          Ollama
          <template #append>
            <v-chip size="x-small" variant="tonal" color="grey" class="ml-1">Soon</v-chip>
          </template>
        </v-chip>
        <v-chip variant="outlined" color="grey" prepend-icon="mdi-code-braces" disabled>
          Codex
          <template #append>
            <v-chip size="x-small" variant="tonal" color="grey" class="ml-1">Soon</v-chip>
          </template>
        </v-chip>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import SettingsClaudeCode from './SettingsClaudeCode.vue'
</script>
