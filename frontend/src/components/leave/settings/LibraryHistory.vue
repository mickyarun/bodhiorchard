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

<!-- The library's own trail: who added, changed or deleted a library type.
     Reloads whenever the library does (the page loads it on mount, and after
     every save or delete), so a change shows up straight away. -->
<template>
  <section class="mt-8" aria-labelledby="library-history">
    <h2 id="library-history" class="text-subtitle-1 font-weight-bold">Library history</h2>
    <p class="text-body-2 text-medium-emphasis mb-2">
      Who added, changed or deleted library types. A change that reached a policy is in that
      policy's History too.
    </p>
    <v-progress-linear v-if="history.loading.value" indeterminate color="primary" class="mb-2" />
    <AppCallout v-if="history.error.value" variant="error">{{ history.error.value }}</AppCallout>
    <p v-else-if="!history.loading.value && !history.events.value.length" class="text-body-2 text-medium-emphasis">
      No changes yet.
    </p>
    <ConfigEventList :events="history.events.value" />
  </section>
</template>

<script setup lang="ts">
import { watch } from 'vue'
import AppCallout from '@/components/common/AppCallout.vue'
import ConfigEventList from '@/components/leave/settings/ConfigEventList.vue'
import { useConfigHistory } from '@/composables/useConfigHistory'
import { useLeaveLibraryStore } from '@/stores/leaveLibrary'

const store = useLeaveLibraryStore()
const history = useConfigHistory()

watch(() => store.entries, () => void history.load('/v1/leave/library-types/history'))
</script>
