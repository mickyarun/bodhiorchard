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
  <div class="chat-panel">
    <div class="chat-header">
      <v-icon icon="mdi-creation-outline" size="18" color="primary" />
      <span class="text-body-2 font-weight-medium flex-grow-1">AI Editor</span>
      <!-- Repo picker — surfaced only when the user is on the design
           section AND more than one design row exists for the BUD.
           Selecting an entry switches both the chat target and the
           visible design sub-tab through the parent (single state
           lives in BUDDesignPanel.activeDesignTab). The chip below
           hides while the picker is shown so the header stays
           uncluttered — the picker label already conveys the
           section context. -->
      <v-select
        v-if="showDesignPicker"
        :model-value="selectedDesignId"
        :items="designOptions"
        item-title="label"
        item-value="id"
        density="compact"
        variant="outlined"
        hide-details
        class="chat-design-picker"
        @update:model-value="(id: string) => emit('select-design', id)"
      />
      <v-chip v-else size="x-small" variant="tonal" color="primary">
        {{ sectionLabel }}
      </v-chip>
      <v-btn
        icon="mdi-plus"
        size="x-small"
        variant="text"
        title="New Session"
        @click="emit('new-session')"
      />
      <v-btn icon="mdi-close" size="x-small" variant="text" @click="emit('close')" />
    </div>

    <div ref="chatContainer" class="chat-messages">
      <div v-if="messages.length === 0" class="chat-empty-state">
        <v-icon icon="mdi-creation-outline" size="32" color="primary" class="mb-2" style="opacity: 0.5" />
        <div class="text-body-2 text-medium-emphasis">
          Ask me to edit the <strong>{{ sectionLabel }}</strong> content.
        </div>
        <div class="text-caption text-medium-emphasis mt-1">
          I can add sections, refine wording, restructure, or answer questions.
        </div>
        <div class="chat-tip mt-4">
          <v-icon icon="mdi-lightning-bolt-outline" size="14" class="mr-1" />
          For faster results, export the markdown and work with an LLM directly on your machine.
        </div>
      </div>
      <div
        v-for="(msg, i) in messages"
        :key="i"
        class="chat-message"
        :class="msg.role"
      >
        <div v-if="msg.userName" class="chat-sender text-caption text-medium-emphasis">
          {{ msg.userName }}
        </div>
        <div class="chat-bubble">
          <div v-if="msg.images?.length" class="chat-images mb-1">
            <img
              v-for="(img, j) in msg.images"
              :key="j"
              :src="img"
              class="chat-image"
              alt="Attached image"
            />
          </div>
          {{ msg.text }}
        </div>
      </div>

      <!-- Thinking indicator -->
      <div v-if="loading" class="chat-message ai">
        <div class="chat-bubble thinking-bubble">
          <div class="d-flex align-center ga-2">
            <v-progress-circular indeterminate size="14" width="2" color="primary" />
            <span class="text-caption">{{ statusMessage || 'Thinking...' }}</span>
          </div>
        </div>
      </div>
    </div>

    <div class="chat-input">
      <!-- Stage-gate banner: BUD is in the wrong status for this section.
           Input is disabled; no optimistic local push. -->
      <v-alert
        v-if="stageGateMessage"
        type="warning"
        density="compact"
        variant="tonal"
        class="mb-2"
      >
        {{ stageGateMessage }}
      </v-alert>
      <!-- Manual retry banner after a second consecutive parse-unparseable error. -->
      <v-alert
        v-else-if="retryPrompt"
        type="error"
        density="compact"
        variant="tonal"
        class="mb-2"
      >
        Reply was malformed. <a href="#" @click.prevent="$emit('retry')">Try again</a>
      </v-alert>
      <!-- Image previews -->
      <div v-if="pastedImages.length" class="image-previews d-flex ga-2 mb-2">
        <div v-for="(img, idx) in pastedImages" :key="idx" class="image-thumb">
          <img :src="img" alt="Pasted image" />
          <v-btn
            icon="mdi-close"
            size="x-small"
            variant="flat"
            color="error"
            class="remove-btn"
            @click="removeImage(idx)"
          />
        </div>
      </div>
      <v-textarea
        v-model="input"
        variant="outlined"
        density="compact"
        rows="2"
        auto-grow
        max-rows="5"
        :placeholder="pastedImages.length ? 'Describe what you want done with the image...' : 'Ask AI to edit this section...'"
        hide-details
        :disabled="loading || !!stageGateMessage"
        @keydown.enter.exact.prevent="sendChat"
        @paste="handlePaste"
      >
        <template #append-inner>
          <v-btn
            icon="mdi-send"
            size="small"
            variant="text"
            color="primary"
            :loading="loading"
            :disabled="!input.trim() && !pastedImages.length || !!stageGateMessage"
            @click="sendChat"
          />
        </template>
      </v-textarea>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, ref, nextTick, watch } from 'vue'

export interface ChatMessage {
  role: 'user' | 'ai'
  text: string
  userName?: string | null
  images?: string[]
}

const props = defineProps<{
  sectionLabel: string
  messages: ChatMessage[]
  loading: boolean
  statusMessage: string
  /** Non-empty when the section is locked by BUD stage (server 409). */
  stageGateMessage?: string
  /** Show the manual retry banner after a second parse failure. */
  retryPrompt?: boolean
  /**
   * Per-repo design rows for the active BUD. Supplied only when the
   * user is on the design section; rendered as a header dropdown
   * when there are 2+ entries so the user can switch which
   * wireframe the chat targets without leaving the chat panel.
   */
  designs?: Array<{ id: string; repoName: string | null }>
  /** Currently-active design row id (matches the design sub-tab). */
  selectedDesignId?: string
}>()

const emit = defineEmits<{
  close: []
  send: [message: string, images: string[]]
  'new-session': []
  retry: []
  'select-design': [designId: string]
}>()

const showDesignPicker = computed(
  () => (props.designs?.length ?? 0) >= 2 && !!props.selectedDesignId,
)
const designOptions = computed(() =>
  (props.designs ?? []).map((d) => ({
    id: d.id,
    label: d.repoName ?? 'general',
  })),
)

const input = ref('')
const chatContainer = ref<HTMLElement | null>(null)
const pastedImages = ref<string[]>([])

const MAX_IMAGES = 3
const MAX_IMAGE_BYTES = 5 * 1024 * 1024 // 5 MB

function handlePaste(event: ClipboardEvent): void {
  const items = event.clipboardData?.items
  if (!items) return

  for (const item of Array.from(items)) {
    if (!item.type.startsWith('image/')) continue
    event.preventDefault()

    if (pastedImages.value.length >= MAX_IMAGES) return

    const blob = item.getAsFile()
    if (!blob || blob.size > MAX_IMAGE_BYTES) return

    const reader = new FileReader()
    reader.onload = () => {
      if (typeof reader.result === 'string') {
        pastedImages.value.push(reader.result)
      }
    }
    reader.readAsDataURL(blob)
  }
}

function removeImage(index: number): void {
  pastedImages.value.splice(index, 1)
}

function sendChat(): void {
  const msg = input.value.trim()
  const images = [...pastedImages.value]
  if ((!msg && !images.length) || props.loading) return
  emit('send', msg || '(image attached)', images)
  input.value = ''
  pastedImages.value = []
  scrollChat()
}

function scrollChat(): void {
  nextTick(() => {
    if (chatContainer.value) {
      chatContainer.value.scrollTop = chatContainer.value.scrollHeight
    }
  })
}

// Auto-scroll when messages change
watch(() => props.messages.length, () => scrollChat())
watch(() => props.loading, () => scrollChat())
</script>

<style scoped>
.chat-panel {
  width: 380px;
  min-width: 380px;
  border-left: 1px solid rgba(var(--v-border-color), var(--v-border-opacity));
  display: flex;
  flex-direction: column;
  height: 100%;
}

.chat-header {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 12px 16px;
  border-bottom: 1px solid rgba(var(--v-border-color), var(--v-border-opacity));
}

.chat-design-picker {
  /* Constrain the picker so it doesn't push the close button off-screen
     on the narrowest chat-panel width (~340px). */
  max-width: 180px;
  min-width: 120px;
}

.chat-messages {
  flex: 1;
  overflow-y: auto;
  padding: 16px;
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.chat-empty-state {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  text-align: center;
  padding: 32px 16px;
  height: 100%;
}

.chat-tip {
  display: flex;
  align-items: center;
  font-size: 11px;
  opacity: 0.5;
}

.chat-message {
  display: flex;
  flex-direction: column;
}

.chat-message.user {
  align-items: flex-end;
}

.chat-message.ai {
  align-items: flex-start;
}

.chat-sender {
  margin-bottom: 2px;
  padding: 0 4px;
}

.chat-bubble {
  max-width: 90%;
  padding: 8px 12px;
  border-radius: 12px;
  font-size: 13px;
  line-height: 1.4;
  white-space: pre-wrap;
  word-break: break-word;
}

.chat-message.user .chat-bubble {
  background: rgb(var(--v-theme-primary));
  color: white;
  border-bottom-right-radius: 4px;
}

.chat-message.ai .chat-bubble {
  background: rgba(var(--v-border-color), 0.08);
  border-bottom-left-radius: 4px;
}

.thinking-bubble {
  opacity: 0.7;
}

.chat-input {
  padding: 12px 16px;
  border-top: 1px solid rgba(var(--v-border-color), var(--v-border-opacity));
}

.image-previews {
  flex-wrap: wrap;
}

.image-thumb {
  position: relative;
  width: 64px;
  height: 64px;
  border-radius: 8px;
  overflow: hidden;
  border: 1px solid rgba(var(--v-border-color), var(--v-border-opacity));
}

.image-thumb img {
  width: 100%;
  height: 100%;
  object-fit: cover;
}

.image-thumb .remove-btn {
  position: absolute;
  top: 2px;
  right: 2px;
  width: 18px;
  height: 18px;
  opacity: 0.8;
}

.chat-images {
  display: flex;
  gap: 6px;
  flex-wrap: wrap;
}

.chat-image {
  max-width: 200px;
  max-height: 150px;
  border-radius: 8px;
  object-fit: contain;
}
</style>
