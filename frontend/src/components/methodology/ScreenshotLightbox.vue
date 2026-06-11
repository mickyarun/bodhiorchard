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

<!-- Click-to-zoom image viewer, shared by the screenshot sections. -->
<template>
  <v-dialog
    :model-value="modelValue"
    max-width="90vw"
    @update:model-value="emit('update:modelValue', $event)"
  >
    <v-card class="screenshot-lightbox" @click="emit('update:modelValue', false)">
      <img :src="src" :alt="alt" class="screenshot-lightbox__img" />
    </v-card>
  </v-dialog>
</template>

<script setup lang="ts">
defineProps<{
  modelValue: boolean
  src: string
  alt: string
}>()

const emit = defineEmits<{
  'update:modelValue': [boolean]
}>()
</script>

<style scoped>
.screenshot-lightbox {
  cursor: zoom-out;
  background: rgba(8, 14, 9, 0.96);
}
.screenshot-lightbox__img {
  display: block;
  width: 100%;
  height: auto;
  max-height: 90vh;
  object-fit: contain;
}
</style>
