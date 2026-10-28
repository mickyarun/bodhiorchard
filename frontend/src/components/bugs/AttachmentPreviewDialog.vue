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

<!-- Full-size view of an image attachment. -->
<template>
  <v-dialog v-model="open" max-width="960">
    <v-card color="surface" class="pa-2">
      <img v-if="url" :src="url" class="preview-image" alt="Attachment preview" />
    </v-card>
  </v-dialog>
</template>

<script setup lang="ts">
defineProps<{ url: string | null }>()
const open = defineModel<boolean>({ required: true })
</script>

<style scoped>
.preview-image {
  display: block;
  width: 100%;
  height: auto;
  border-radius: 4px;
}
</style>
