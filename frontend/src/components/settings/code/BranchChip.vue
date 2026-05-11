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
  Tiny chip used inside RepoList to render either the configured
  branch name or a "Set X" hint when unmapped. Clickable so the user
  can open the branch-mapping dialog directly from any chip — both
  the configured one and the "Set UAT" fallback.
-->
<template>
  <v-chip
    size="x-small"
    :variant="resolved ? 'tonal' : 'outlined'"
    :color="resolved ? (muted ? 'grey' : 'primary') : 'warning'"
    class="text-truncate branch-chip"
    :class="{ 'branch-chip--locked': disabled }"
    @click="onClick"
  >
    <v-icon :icon="icon" size="12" start />
    {{ resolved || fallback }}
  </v-chip>
</template>

<script setup lang="ts">
import { computed } from 'vue'

const props = defineProps<{
  icon: string
  label: string | null
  fallback: string
  muted?: boolean
  disabled?: boolean
}>()

const emit = defineEmits<{ click: [] }>()

const resolved = computed(() => props.label || '')

function onClick(): void {
  if (props.disabled) return
  emit('click')
}
</script>

<style scoped>
.branch-chip {
  cursor: pointer;
}
.branch-chip--locked {
  cursor: not-allowed;
  opacity: 0.55;
  pointer-events: auto; /* keep the cursor visible; click is intercepted in JS */
}
</style>
