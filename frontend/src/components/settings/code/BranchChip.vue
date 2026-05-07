<!--
  SPDX-License-Identifier: AGPL-3.0-or-later
  Copyright (C) 2026 Arun Rajkumar

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
