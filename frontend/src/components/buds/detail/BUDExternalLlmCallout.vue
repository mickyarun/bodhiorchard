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

<!-- Shown when every stage agent is off for this BUD: the person drives
     each stage from their own local AI through the remote MCP endpoint,
     which can write back through the assignee-only update_bud tool, or
     pastes the finished section into the editor. -->
<template>
  <AppCallout variant="info" title="Stage agents are off. You're driving this BUD." icon="mdi-laptop-account">
    Your local AI can write the Requirements, Design and Tech spec through MCP Connect (assignee only,
    current stage only), or you can paste a finished section into the editor. Turn individual stages back
    to automatic under AI skills.
    <template #actions>
      <v-btn size="small" variant="text" prepend-icon="mdi-tune-variant" @click="emit('open-skill-settings')">
        AI skills
      </v-btn>
      <v-btn size="small" variant="outlined" prepend-icon="mdi-connection" :to="{ name: 'settings-mcp-connect' }">
        MCP Connect
      </v-btn>
    </template>
  </AppCallout>
</template>

<script setup lang="ts">
import AppCallout from '@/components/common/AppCallout.vue'

const emit = defineEmits<{ 'open-skill-settings': [] }>()
</script>
