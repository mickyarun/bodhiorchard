<!--
  SPDX-License-Identifier: AGPL-3.0-or-later
  Copyright (C) 2026 Arun Rajkumar

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
