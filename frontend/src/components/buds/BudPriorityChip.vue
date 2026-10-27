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

<!-- P0–P3 tag: the priority hue as text on a wash of itself. -->
<template>
  <span class="bud-priority" :style="{ '--priority': `var(--v-theme-${BUD_PRIORITY_COLORS[priority]})` }">
    <span class="d-sr-only">Priority </span>{{ priority }}
  </span>
</template>

<script setup lang="ts">
import { BUD_PRIORITY_COLORS, type BUDPriority } from '@/types'

defineProps<{ priority: BUDPriority }>()
</script>

<style scoped>
.bud-priority {
  display: inline-flex;
  align-items: center;
  flex-shrink: 0;
  padding: 1px 6px;
  border-radius: 5px;
  font: 600 11px/16px var(--font-mono);
  color: rgb(var(--priority));
  background: rgba(var(--priority), 0.14);
}
</style>
