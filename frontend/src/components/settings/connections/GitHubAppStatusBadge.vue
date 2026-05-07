<!--
  SPDX-License-Identifier: AGPL-3.0-or-later
  Copyright (C) 2026 Arun Rajkumar

  Tiny presentational chip that mirrors the GitHub App lifecycle state.
  Splits out of GitHubAppConnectionCard so the orchestrator file can
  stay under the project's 200-line ceiling.
-->
<template>
  <v-chip :color="color" size="x-small" variant="tonal">
    {{ label }}
  </v-chip>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { GITHUB_APP_STATUS, type GitHubAppStatus } from '@/types/connections'

const props = defineProps<{ status: GitHubAppStatus }>()

const color = computed(() => {
  switch (props.status) {
    case GITHUB_APP_STATUS.READY:
      return 'success'
    case GITHUB_APP_STATUS.AWAITING_INSTALL:
      return 'warning'
    default:
      return 'grey'
  }
})

const label = computed(() => {
  switch (props.status) {
    case GITHUB_APP_STATUS.READY:
      return 'Connected'
    case GITHUB_APP_STATUS.AWAITING_INSTALL:
      return 'Install pending'
    default:
      return 'Not set up'
  }
})
</script>
