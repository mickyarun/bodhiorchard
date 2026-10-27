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

<!-- The AI chat side panel for the open section, fed by the page's
     useBudDetailChat controller. -->
<template>
  <transition name="slide-panel">
    <ChatPanel
      v-if="chatOpen"
      :section-label="sectionLabel"
      :messages="chatMessages"
      :loading="chatLoading"
      :status-message="chatStatusMessage"
      :stage-gate-message="stageGateMessage"
      :chat-in-progress-banner="chatInProgressBanner"
      :retry-prompt="retryPrompt"
      :designs="chatDesignOptions"
      :selected-design-id="selectedDesignId ?? undefined"
      :needs-design-generation="needsDesignGeneration"
      @close="chatOpen = false"
      @send="handleChatSend"
      @cancel="handleChatCancel"
      @new-session="startNewSession"
      @retry="manualRetry"
      @select-design="emit('select-design', $event)"
      @open-generate-designs="openGenerateDesigns"
      @open-autogen-settings="emit('open-autogen-settings')"
    />
  </transition>
</template>

<script setup lang="ts">
import ChatPanel from '@/components/buds/ChatPanel.vue'
import type { useBudDetailChat } from '@/composables/useBudDetailChat'

const props = defineProps<{
  chat: ReturnType<typeof useBudDetailChat>
  sectionLabel: string
  needsDesignGeneration: boolean
  selectedDesignId?: string | null
}>()

const emit = defineEmits<{ 'select-design': [designId: string]; 'open-autogen-settings': [] }>()

// ``chat`` is a plain object of refs from one composable call that lives as
// long as the page, so destructuring keeps reactivity (the same pattern as
// BUDStatusDialogs and its controller).
const {
  chatOpen, chatLoading, chatMessages, chatStatusMessage, stageGateMessage, chatInProgressBanner, retryPrompt,
  chatDesignOptions, handleChatSend, handleChatCancel, startNewSession, manualRetry, openGenerateDesigns,
} = props.chat
</script>

<style scoped>
.slide-panel-enter-active,
.slide-panel-leave-active {
  transition: all var(--dur-mid) ease;
}
.slide-panel-enter-from,
.slide-panel-leave-to {
  width: 0;
  min-width: 0;
  opacity: 0;
}
</style>
