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

<!-- Who shipped the most BUDs in the last 30 days, with their commit and
     merged pull request totals across those BUDs. -->
<template>
  <AppPanel title="Top contributors" note="Last 30 days, by BUDs shipped" flush>
    <p v-if="contributors.length === 0" class="contrib-empty">
      No closed BUDs with contributors in the last 30 days.
    </p>
    <ol v-else class="contribs">
      <li v-for="row in contributors" :key="row.user_id" class="contrib">
        <AppMonogram :name="row.name" />
        <span class="contrib__who">
          <span class="contrib__name">{{ row.name }}</span>
          <span class="contrib__stats">
            {{ plural(row.total_commits_30d, 'commit') }} · {{ plural(row.total_prs_merged_30d, 'pull request') }} merged
          </span>
        </span>
        <span class="contrib__count">{{ plural(row.buds_shipped_30d, 'BUD') }}</span>
      </li>
    </ol>
  </AppPanel>
</template>

<script setup lang="ts">
import AppMonogram from '@/components/common/AppMonogram.vue'
import AppPanel from '@/components/common/AppPanel.vue'
import type { TopContributor } from '@/composables/useLearningsOverview'
import { plural } from '@/utils/format'

defineProps<{ contributors: TopContributor[] }>()
</script>

<style scoped>
.contrib-empty {
  margin: 0;
  padding: 0 20px 18px;
  font-size: 13px;
  color: rgb(var(--v-theme-ink-2));
}
.contribs {
  list-style: none;
  margin: 0;
  padding: 0;
}
.contrib {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 12px 20px;
  border-top: 1px solid rgb(var(--v-theme-rule));
}
.contrib__who {
  display: flex;
  flex-direction: column;
  flex: 1 1 auto;
  min-width: 0;
}
.contrib__name {
  font-size: 14px;
  font-weight: 500;
}
.contrib__stats {
  font-size: 12px;
  color: rgb(var(--v-theme-on-surface-variant));
}
.contrib__count {
  flex-shrink: 0;
  font-size: 13px;
  font-weight: 600;
  font-variant-numeric: tabular-nums;
}
</style>
