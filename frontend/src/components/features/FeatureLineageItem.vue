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

<!-- "Created Oct 3 by PR #12": one lineage line on a feature card. The
     source is a link when it's a tracked PR. -->
<template>
  <span class="lineage-item" :title="formatDateTime(at)">
    {{ verb }} {{ formatDate(at) }}
    <template v-if="row.byLabel">
      by
      <a v-if="row.prUrl" :href="row.prUrl" target="_blank" rel="noopener">
        {{ row.byLabel }}<span class="d-sr-only"> (opens in a new tab)</span>
      </a>
      <span v-else>{{ row.byLabel }}</span>
    </template>
  </span>
</template>

<script setup lang="ts">
import { formatDate, formatDateTime } from '@/utils/date'
import type { LineageRow } from '@/utils/featureCard'

defineProps<{ verb: string; at: string; row: LineageRow }>()
</script>

<style scoped>
.lineage-item a {
  color: var(--color-accent-text);
  text-decoration: none;
}
.lineage-item a:hover {
  text-decoration: underline;
}
</style>
