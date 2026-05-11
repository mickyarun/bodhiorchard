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
