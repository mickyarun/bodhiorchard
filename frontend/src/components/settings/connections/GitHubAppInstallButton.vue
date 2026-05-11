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
  AWAITING_INSTALL CTA — opens GitHub's app-install URL in a new tab.
  Disabled (with explanation) when the backend hasn't surfaced an
  install URL yet, e.g. because the App slug is missing.
-->
<template>
  <div class="d-flex flex-column ga-2">
    <v-btn
      color="primary"
      size="large"
      :href="installUrl ?? undefined"
      :disabled="!installUrl"
      target="_blank"
      rel="noopener noreferrer"
      prepend-icon="mdi-github"
      block
    >
      Install on GitHub
    </v-btn>
    <div class="text-caption text-medium-emphasis">
      <v-icon icon="mdi-information-outline" size="14" class="mr-1" />
      Credentials saved. Finish by installing the App on your GitHub org —
      this page will refresh automatically when the install webhook lands.
    </div>
  </div>
</template>

<script setup lang="ts">
defineProps<{ installUrl: string | null }>()
</script>
