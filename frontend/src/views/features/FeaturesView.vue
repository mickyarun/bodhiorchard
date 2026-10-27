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

<!-- Features: what the product already does, mapped from the code. Shows
     the setup steps while nothing is mapped, otherwise filters and a grid
     of feature cards. -->
<template>
  <AppPage title="Features" :subtitle="subtitle">
    <FeatureFilters
      v-model:query="query"
      v-model:repo-id="repoId"
      v-model:mode="mode"
      v-model:touched-sort="touchedSort"
      :repos="activeRepos"
    />

    <v-progress-linear :active="store.loading && hasLoadedOnce" indeterminate color="primary" height="2" />

    <AppCallout v-if="store.error" variant="error" title="Features didn't load">
      {{ store.error }}
      <template #actions><v-btn variant="outlined" size="small" @click="reload">Retry</v-btn></template>
    </AppCallout>

    <AppCallout v-if="focusedId" variant="info">
      Showing one feature, linked from a BUD.
      <template #actions><v-btn variant="text" size="small" @click="clearFocus">Show all features</v-btn></template>
    </AppCallout>

    <div v-if="!hasLoadedOnce" class="features-page__loading">
      <v-progress-circular indeterminate color="primary" aria-label="Loading features" />
    </div>

    <template v-else-if="!store.loading || store.items.length">
      <FeaturesEmptyState v-if="nothingMapped" :repos="settingsStore.repos" :can-configure="canViewCodeSettings" />

      <p v-else-if="store.items.length === 0" class="features-page__none">
        {{ emptyListText({ searching: !!query.trim(), repoFiltered: !!repoId, mode }) }}
      </p>

      <template v-else>
        <TopContributorsPanel v-if="repoId" :contributors="contributors" :loading="contributorsLoading" />
        <div class="features-page__grid">
          <FeatureCard v-for="feature in store.items" :key="feature.id" :feature="feature" />
        </div>
        <v-pagination v-if="pageCount > 1" v-model="page" :length="pageCount" :total-visible="5" density="comfortable" />
      </template>
    </template>
  </AppPage>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import AppCallout from '@/components/common/AppCallout.vue'
import AppPage from '@/components/common/AppPage.vue'
import FeatureCard from '@/components/features/FeatureCard.vue'
import FeatureFilters from '@/components/features/FeatureFilters.vue'
import FeaturesEmptyState from '@/components/features/FeaturesEmptyState.vue'
import TopContributorsPanel from '@/components/features/TopContributorsPanel.vue'
import { useFeatureList } from '@/composables/useFeatureList'
import { usePermissions } from '@/composables/usePermissions'
import { useSettingsStore } from '@/stores/settings'
import { emptyListText } from '@/utils/featureSetup'

const {
  store, repoId, query, mode, touchedSort, page, pageCount, hasLoadedOnce, focusedId,
  activeRepos, nothingMapped, contributors, contributorsLoading, clearFocus, reload,
} = useFeatureList()
const settingsStore = useSettingsStore()
const { canViewCodeSettings } = usePermissions()

const MODE_NOUN: Record<string, [string, string]> = {
  active: ['live feature', 'live features'],
  all: ['feature', 'features'],
  in_progress: ['feature in progress', 'features in progress'],
  deactivated: ['deactivated feature', 'deactivated features'],
}

// "12 live features across 3 repositories", scoped to the repository filter.
const subtitle = computed(() => {
  if (!hasLoadedOnce.value || nothingMapped.value) return 'What your product already does, mapped from your code'
  const n = store.total
  const [one, many] = MODE_NOUN[mode.value]
  const count = `${n} ${n === 1 ? one : many}`
  const repo = activeRepos.value.find(r => r.id === repoId.value)
  if (repo) return `${count} in ${repo.name}`
  const repos = activeRepos.value.length
  return repos ? `${count} across ${repos} ${repos === 1 ? 'repository' : 'repositories'}` : count
})
</script>

<style scoped>
.features-page__loading {
  display: flex;
  justify-content: center;
  padding: 56px 0;
}
.features-page__none {
  margin: 0;
  padding: 40px 16px;
  text-align: center;
  font-size: 14px;
  color: rgb(var(--v-theme-on-surface-variant));
  background: rgb(var(--v-theme-surface));
  border: 1px solid rgb(var(--v-theme-rule));
  border-radius: 12px;
}
.features-page__grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(min(100%, 340px), 1fr));
  gap: 14px;
  align-items: start;
}
</style>
