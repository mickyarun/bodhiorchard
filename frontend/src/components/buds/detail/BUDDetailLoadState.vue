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

<!-- The BUD detail page before the BUD is on screen: a skeleton in the
     page's shape while it loads (reads as "forming", not as a hang), or
     the load error with a way back and a retry. -->
<template>
  <div v-if="loading" class="load-state">
    <v-skeleton-loader type="heading" />
    <v-skeleton-loader type="text" width="35%" />
    <v-skeleton-loader type="button@5" />
    <v-skeleton-loader type="paragraph@4" />
  </div>
  <AppCallout v-else variant="error" title="This BUD didn't load">
    {{ error }}
    <template #actions>
      <v-btn variant="text" size="small" to="/buds">Back to board</v-btn>
      <v-btn variant="outlined" size="small" @click="emit('retry')">Retry</v-btn>
    </template>
  </AppCallout>
</template>

<script setup lang="ts">
import AppCallout from '@/components/common/AppCallout.vue'

defineProps<{ loading: boolean; error: string }>()
const emit = defineEmits<{ retry: [] }>()
</script>

<style scoped>
.load-state {
  display: flex;
  flex-direction: column;
  gap: 20px;
}
</style>
