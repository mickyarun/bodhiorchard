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

<!-- The people with the most commits in the selected repository. -->
<template>
  <AppPanel v-if="contributors.length > 0 || loading" title="Top contributors" note="By commits in this repository">
    <div v-if="loading && contributors.length === 0" class="contrib__loading">
      <v-progress-circular indeterminate size="18" width="2" color="primary" aria-label="Loading contributors" />
    </div>
    <ol v-else class="contrib__list">
      <li v-for="(c, i) in contributors" :key="(c.userId ?? c.actorName) + '-' + i" class="contrib__row">
        <AppMonogram :name="c.actorName" :src="c.avatarUrl" :size="28" />
        <span class="contrib__body">
          <span class="contrib__name">{{ c.actorName }}</span>
          <span class="contrib__stats">
            {{ plural(c.commitCount, 'commit') }} · {{ plural(c.filesChanged, 'file') }}
          </span>
        </span>
      </li>
    </ol>
  </AppPanel>
</template>

<script setup lang="ts">
import AppMonogram from '@/components/common/AppMonogram.vue'
import AppPanel from '@/components/common/AppPanel.vue'
import type { RepoContributor } from '@/types'
import { plural } from '@/utils/format'

defineProps<{ contributors: RepoContributor[]; loading: boolean }>()
</script>

<style scoped>
.contrib__loading {
  display: flex;
}
.contrib__list {
  list-style: none;
  margin: 0;
  padding: 0;
  display: flex;
  flex-wrap: wrap;
  gap: 12px 24px;
}
.contrib__row {
  display: flex;
  align-items: center;
  gap: 10px;
  min-width: 0;
}
.contrib__body {
  display: flex;
  flex-direction: column;
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
</style>
