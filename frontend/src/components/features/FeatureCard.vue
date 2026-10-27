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

<!-- One feature: title and lifecycle tag, where it comes from (repository
     or BUD, plus backend repositories it calls), description, tags, when it
     was created and last touched, and an expandable detail. -->
<template>
  <article class="feature-card" :class="{ 'feature-card--off': !feature.isActive }">
    <header class="feature-card__head">
      <h3 class="feature-card__title">{{ featureDisplayTitle(feature) }}</h3>
      <AppTag :color="lifecycle.color" sr-prefix="Status:">{{ lifecycle.label }}</AppTag>
    </header>

    <div v-if="origins.length" class="feature-card__origins">
      <span v-for="o in origins" :key="o.key" class="feature-card__origin" :title="o.title">
        <v-icon :icon="o.icon" size="13" aria-hidden="true" />{{ o.label }}
      </span>
    </div>

    <p v-if="off" class="feature-card__off">
      Deactivated {{ off.dateLabel }}
      <template v-if="off.prNumber">
        in <a v-if="off.prUrl" :href="off.prUrl" target="_blank" rel="noopener">PR #{{ off.prNumber }}</a>
        <template v-else>PR #{{ off.prNumber }}</template>
      </template>
      <template v-else-if="off.shortSha">in commit <code>{{ off.shortSha }}</code></template>
    </p>

    <p class="feature-card__desc" :class="{ 'feature-card__desc--full': expanded }">{{ feature.description }}</p>

    <ul v-if="feature.tags.length" class="feature-card__tags" aria-label="Tags">
      <li v-for="tag in feature.tags.slice(0, 6)" :key="tag">{{ tag }}</li>
    </ul>

    <div class="feature-card__lineage">
      <FeatureLineageItem verb="Created" :at="feature.createdAt" :row="lineage.created" />
      <FeatureLineageItem v-if="showLastTouched(feature)" verb="Last touched" :at="feature.updatedAt" :row="lineage.lastSeen" />
    </div>

    <v-btn
      v-if="hasDetail"
      variant="text"
      size="small"
      class="feature-card__toggle"
      :aria-expanded="expanded"
      :append-icon="expanded ? 'mdi-chevron-up' : 'mdi-chevron-down'"
      @click="expanded = !expanded"
    >
      {{ expanded ? 'Hide details' : 'Show details' }}
    </v-btn>
    <v-expand-transition>
      <FeatureCardDetail v-if="expanded" :feature="feature" />
    </v-expand-transition>
  </article>
</template>

<script setup lang="ts">
import { computed, ref } from 'vue'
import AppTag from '@/components/common/AppTag.vue'
import type { Feature } from '@/types'
import {
  deactivatedSummary,
  featureDisplayTitle,
  featureHasDetail,
  featureLifecycle,
  featureLineage,
  showLastTouched,
} from '@/utils/featureCard'
import FeatureCardDetail from './FeatureCardDetail.vue'
import FeatureLineageItem from './FeatureLineageItem.vue'

const props = defineProps<{ feature: Feature }>()
const expanded = ref(false)

const lifecycle = computed(() => featureLifecycle(props.feature))
const lineage = computed(() => featureLineage(props.feature))
const off = computed(() => deactivatedSummary(props.feature))
const hasDetail = computed(() => featureHasDetail(props.feature))

// Where the feature comes from: its repository, or the BUD that planned it
// before any code landed; then each backend repository it calls.
const origins = computed(() => {
  const f = props.feature
  const out: Array<{ key: string; icon: string; label: string; title: string }> = []
  if (f.primary) {
    out.push({ key: 'primary', icon: 'mdi-source-repository', label: f.primary.repoName, title: 'Repository' })
  } else if (f.source === 'bud' && f.sourceRef) {
    out.push({ key: 'bud', icon: 'mdi-file-document-outline', label: f.sourceRef, title: `Planned in ${f.sourceRef}` })
  }
  for (const link of f.backendLinks) {
    const paths = link.apiPaths.length === 1 ? '1 API path' : `${link.apiPaths.length} API paths`
    out.push({ key: link.repoId, icon: 'mdi-arrow-right', label: link.repoName, title: `Calls ${link.repoName} · ${paths}` })
  }
  return out
})
</script>

<style scoped>
.feature-card {
  display: flex;
  flex-direction: column;
  gap: 10px;
  min-width: 0;
  padding: 18px 20px;
  background: rgb(var(--v-theme-surface));
  border: 1px solid rgb(var(--v-theme-rule));
  border-radius: 12px;
}
.feature-card--off .feature-card__title,
.feature-card--off .feature-card__desc {
  color: rgb(var(--v-theme-on-surface-variant));
}
.feature-card__head {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 12px;
}
.feature-card__title {
  margin: 0;
  min-width: 0;
  font-size: 15px;
  line-height: 22px;
  font-weight: 600;
  overflow-wrap: anywhere;
}
.feature-card__origins,
.feature-card__tags {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}
.feature-card__origin {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  max-width: 100%;
  font: 500 12px/18px var(--font-mono);
  color: rgb(var(--v-theme-ink-2));
  overflow-wrap: anywhere;
}
.feature-card__off,
.feature-card__desc {
  margin: 0;
  font-size: 14px;
  line-height: 21px;
}
.feature-card__off {
  font-size: 13px;
  color: rgb(var(--v-theme-on-surface-variant));
}
.feature-card__off a {
  color: var(--color-accent-text);
}
.feature-card__desc {
  color: rgb(var(--v-theme-ink-2));
  display: -webkit-box;
  -webkit-line-clamp: 4;
  -webkit-box-orient: vertical;
  overflow: hidden;
}
.feature-card__desc--full {
  -webkit-line-clamp: unset;
}
.feature-card__tags {
  list-style: none;
  margin: 0;
  padding: 0;
}
.feature-card__tags li {
  padding: 1px 8px;
  border-radius: 999px;
  font-size: 12px;
  color: rgb(var(--v-theme-ink-2));
  background: rgb(var(--v-theme-surface-variant));
}
.feature-card__lineage {
  display: flex;
  flex-wrap: wrap;
  gap: 4px 14px;
  font-size: 12px;
  color: rgb(var(--v-theme-on-surface-variant));
}
.feature-card__toggle {
  align-self: flex-start;
  margin: -4px 0 -8px -8px;
}
</style>
