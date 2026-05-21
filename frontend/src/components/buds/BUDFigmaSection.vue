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

<!--
  Figma-URL section of the Design tab.

  Two responsibilities, no more:
  - Capture a Figma file URL on the BUD (PATCH ``bud.figma_url``,
    save on blur).
  - Render Figma's iframe embed when the URL parses cleanly; an
    AppCallout warning when it doesn't.

  This component is shown INSTEAD OF the existing AI-wireframe flow
  whenever ``bud.figma_url`` is set — see ``BUDDesignPanel.vue``'s
  top-level v-if. We don't try to coexist on the same BUD: the design
  source is whichever path the PM chose.
 -->

<template>
  <div class="figma-section pa-4">
    <v-text-field
      :model-value="bud.figma_url || ''"
      label="Figma file URL"
      placeholder="https://www.figma.com/design/<key>/<name>"
      variant="outlined"
      density="comfortable"
      hide-details="auto"
      persistent-placeholder
      :readonly="!editable"
      prepend-inner-icon="mdi-link"
      class="mb-3"
      @update:model-value="handleUrlInput"
    />

    <div class="text-caption text-medium-emphasis mb-4">
      Accepts <code>/file/</code>, <code>/design/</code>, or
      <code>/proto/</code> URL shapes from figma.com. The Tech-Arch tab
      uses this URL to drive its local-Claude tech-spec prompt.
    </div>

    <!--
      Parse-failure path: surface a clear AppCallout with the URL the
      user actually pasted so the typo is obvious. We deliberately
      avoid v-alert (per AppCallout/AppPillToggle conventions).
     -->
    <AppCallout
      v-if="bud.figma_url && !embedUrl"
      variant="warning"
      eyebrow="Couldn't read URL"
      icon="mdi-link-off"
      class="mb-3"
    >
      <code>{{ bud.figma_url }}</code> isn't a recognisable Figma share
      URL. Re-copy from Figma's Share dialog (the "Copy link" button)
      and paste again.
    </AppCallout>

    <!--
      Iframe sandbox flags (minimum safe set):
      - ``allow-scripts``: Figma's embed is a JS app — without this
        the iframe loads but nothing renders.
      - ``allow-same-origin``: Figma's session cookies must travel
        with the iframe for private files; without it the user sees
        a permanent login prompt.
      We explicitly omit ``allow-forms`` / ``allow-popups`` /
      ``allow-top-navigation`` so the embed cannot navigate the host
      app or open new windows under our origin.

      Load-state UX: the iframe is ALWAYS in the DOM with the spinner
      overlaid on top (absolute positioning + opaque background). We
      deliberately don't hide the iframe via ``v-show`` while loading
      — display:none stops the browser from fetching the iframe's
      source, the ``load`` event never fires, and the spinner sticks
      forever. The overlay pattern lets the iframe load eagerly while
      we still cover Figma's initial blank-white render.

      The wrapper's ``:key="embedUrl"`` forces a fresh iframe element
      on every URL change so the ``load`` event reliably fires for
      the new URL even when the source string just changed values.

      No ``loading="lazy"``: same reason as the v-show issue — lazy
      iframes don't fetch until in-viewport, which fights the overlay.
     -->
    <div v-if="embedUrl" :key="embedUrl" class="figma-embed-frame">
      <iframe
        :src="embedUrl"
        class="figma-iframe"
        sandbox="allow-scripts allow-same-origin"
        title="Figma file preview"
        @load="iframeLoading = false"
      />
      <div v-if="iframeLoading" class="figma-loading">
        <v-progress-circular indeterminate color="secondary" size="32" width="3" />
        <div class="text-caption text-medium-emphasis mt-2">
          Loading Figma preview…
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, ref, watch } from 'vue'

import AppCallout from '@/components/common/AppCallout.vue'
import { useBUDStore } from '@/stores/bud'
import type { BUDDocument } from '@/types'
import { toEmbedUrl } from '@/utils/figmaEmbed'

const props = withDefaults(
  defineProps<{
    bud: BUDDocument
    // Mirrors BUDDesignPanel's editable contract — only writable while
    // the BUD is in DESIGN status. Outside that, the field renders
    // read-only and blur saves are skipped.
    editable?: boolean
  }>(),
  { editable: true },
)

const budStore = useBUDStore()

const embedUrl = computed(() => toEmbedUrl(props.bud.figma_url))

// Overlay a spinner on top of the iframe whenever the embed URL
// flips to a new value. Cleared on the iframe's ``load`` event
// (template: ``@load="iframeLoading = false"``) OR after the safety
// timeout below — whichever fires first. The timeout exists because
// Figma's embed handshake can fail silently on private files (no
// load event ever fires; the iframe just renders Figma's own login
// prompt). A stuck spinner over a usable iframe is worse than no
// spinner; better to clear it and let the user see whatever Figma
// has actually rendered.
const iframeLoading = ref(false)
let loadingTimer: ReturnType<typeof setTimeout> | null = null

// 8s is well past Figma's typical embed handshake (1–3s on a warm
// connection). Bumping further risks the spinner outlasting the user's
// attention; pulling lower risks clearing the spinner before the
// iframe paints on a slow connection. Adjust if real-world telemetry
// suggests a different threshold.
const _IFRAME_LOAD_TIMEOUT_MS = 8000

watch(
  embedUrl,
  (next, prev) => {
    if (loadingTimer) {
      clearTimeout(loadingTimer)
      loadingTimer = null
    }
    if (next && next !== prev) {
      iframeLoading.value = true
      loadingTimer = setTimeout(() => {
        iframeLoading.value = false
        loadingTimer = null
      }, _IFRAME_LOAD_TIMEOUT_MS)
    }
  },
  { immediate: true },
)

// Debounced save-on-input so the iframe re-renders within ~half a
// second of the user finishing their paste / type, with no extra click
// or blur required. Critical UX: a Figma URL is typically pasted
// whole, not typed character-by-character, so the debounce mostly
// guards against the v-model firing multiple times during paste +
// the user's potential follow-up trim. 500ms is the smallest delay
// that still feels intentional rather than thrashy.
const _SAVE_DEBOUNCE_MS = 500
let saveTimer: ReturnType<typeof setTimeout> | null = null

function handleUrlInput(value: string): void {
  if (!props.editable) return
  if (saveTimer) clearTimeout(saveTimer)
  saveTimer = setTimeout(() => {
    saveTimer = null
    const normalised = value.trim()
    const current = (props.bud.figma_url || '').trim()
    // No-op when nothing changed — avoids spurious PATCH requests when
    // the user merely tabs through the field.
    if (normalised === current) return
    // Empty string clears the URL (column is nullable; the BUDUpdate
    // schema's validator normalises ``""`` → ``None`` server-side).
    // Fire-and-forget — the store updates currentBUD reactively and
    // the prop flows back through, retriggering the embedUrl computed
    // and the iframe wrapper.
    void budStore.updateBUD(props.bud.id, { figma_url: normalised || null })
  }, _SAVE_DEBOUNCE_MS)
}
</script>

<style scoped>
.figma-section {
  display: flex;
  flex-direction: column;
  min-height: 0;
}

.figma-embed-frame {
  position: relative;
  width: 100%;
  height: 70vh;
}

.figma-iframe {
  width: 100%;
  height: 100%;
  border: 1px solid rgb(var(--v-theme-outline-variant));
  border-radius: 4px;
  background: rgb(var(--v-theme-surface));
}

.figma-loading {
  position: absolute;
  inset: 0;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  border: 1px solid rgb(var(--v-theme-outline-variant));
  border-radius: 4px;
  background: rgb(var(--v-theme-surface));
}
</style>
