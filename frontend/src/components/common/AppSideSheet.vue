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

<!-- A modal panel that slides in from the right edge, full screen on
     phones: a title row with a close button, a scrolling body and an
     optional footer for actions.

       <AppSideSheet v-model="open" title="Request leave">
         …form…
         <template #actions><v-btn …>Send</v-btn></template>
       </AppSideSheet>

     It's a dialog, so it sits in the overlay layer: nothing is rendered
     beside the page while it's closed, and focus stays inside while open. -->
<template>
  <v-dialog
    :model-value="modelValue"
    :fullscreen="xs"
    :width="xs ? undefined : width"
    transition="slide-x-reverse-transition"
    content-class="app-side-sheet"
    scrollable
    :aria-labelledby="headingId"
    @update:model-value="emit('update:modelValue', $event)"
  >
    <section class="app-side-sheet__panel">
      <header class="app-side-sheet__head">
        <h2 :id="headingId" class="app-side-sheet__title">{{ title }}</h2>
        <v-btn icon="mdi-close" variant="text" size="small" aria-label="Close" @click="emit('update:modelValue', false)" />
      </header>
      <div class="app-side-sheet__body"><slot /></div>
      <footer v-if="$slots.actions" class="app-side-sheet__foot"><slot name="actions" /></footer>
    </section>
  </v-dialog>
</template>

<script setup lang="ts">
import { useId } from 'vue'
import { useDisplay } from 'vuetify'

withDefaults(defineProps<{ modelValue: boolean; title: string; width?: number }>(), { width: 460 })
const emit = defineEmits<(e: 'update:modelValue', value: boolean) => void>()

const { xs } = useDisplay()
const headingId = useId()
</script>

<!-- Not scoped: the dialog content is teleported to the overlay container. -->
<style>
.v-dialog > .v-overlay__content.app-side-sheet {
  position: absolute;
  top: 0;
  right: 0;
  bottom: 0;
  margin: 0;
  height: 100%;
  max-height: 100%;
  max-width: 100%;
}
.app-side-sheet__panel {
  display: flex;
  flex-direction: column;
  height: 100%;
  background: rgb(var(--v-theme-surface));
  color: rgb(var(--v-theme-on-surface));
  border-left: 1px solid rgb(var(--v-theme-rule));
}
.app-side-sheet__head {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 20px 20px 4px 28px;
}
.app-side-sheet__title {
  margin: 0;
  flex-grow: 1;
  font-size: var(--text-md);
  font-weight: 600;
}
.app-side-sheet__body {
  flex: 1 1 auto;
  overflow-y: auto;
  padding: 16px 28px 24px;
}
.app-side-sheet__foot {
  display: flex;
  justify-content: flex-end;
  flex-wrap: wrap;
  gap: 8px;
  padding: 16px 28px;
  border-top: 1px solid rgb(var(--v-theme-rule));
}
@media (max-width: 600px) {
  .app-side-sheet__head {
    padding: 16px 12px 4px 16px;
  }
  .app-side-sheet__body,
  .app-side-sheet__foot {
    padding-left: 16px;
    padding-right: 16px;
  }
}
</style>
