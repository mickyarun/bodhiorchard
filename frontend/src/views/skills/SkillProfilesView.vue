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

<template>
  <AppPage title="Skills" subtitle="Who knows which part of the code, read from git history. Updated with each repository scan.">
    <template #actions>
      <v-text-field
        v-model="search"
        :label="viewMode === 'people' ? 'Find a person or area' : 'Find an area or person'"
        prepend-inner-icon="mdi-magnify"
        variant="outlined"
        density="compact"
        hide-details
        clearable
        class="skills-search"
        @click:clear="search = ''"
      />
      <AppPillToggle v-model="viewMode" :options="VIEW_OPTIONS" aria-label="Group by" />
    </template>

    <AppCallout v-if="store.error" variant="error">{{ store.error }}</AppCallout>

    <div v-if="store.loading" class="skills-loading">
      <v-progress-circular indeterminate color="primary" aria-label="Loading skills" />
    </div>

    <AppCallout
      v-else-if="!store.error && store.profiles.length === 0"
      variant="info"
      title="No skills yet"
      icon="mdi-account-search-outline"
    >
      Skills come from git history. Scan a repository from Settings, Code and each person's
      areas show up here.
    </AppCallout>

    <template v-else-if="store.profiles.length > 0">
      <p class="skills-count">{{ countLine }}</p>
      <div v-if="viewMode === 'people'" class="skills-grid">
        <SkillPersonCard v-for="profile in people" :key="profile.email" :profile="profile" />
      </div>
      <div v-else class="skills-grid">
        <SkillAreaCard v-for="area in areas" :key="area.name" :area="area" />
      </div>
      <p v-if="shownCount === 0" class="skills-none">Nothing matches "{{ search }}".</p>
    </template>
  </AppPage>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import AppCallout from '@/components/common/AppCallout.vue'
import AppPage from '@/components/common/AppPage.vue'
import AppPillToggle from '@/components/common/AppPillToggle.vue'
import SkillAreaCard from '@/components/skills/SkillAreaCard.vue'
import SkillPersonCard from '@/components/skills/SkillPersonCard.vue'
import { useSkillsStore } from '@/stores/skills'
import { plural } from '@/utils/format'
import { filterAreas, filterProfiles, groupByArea } from '@/utils/skillProfiles'

type ViewMode = 'people' | 'areas'

const VIEW_OPTIONS: { label: string; value: ViewMode }[] = [
  { label: 'By person', value: 'people' },
  { label: 'By area', value: 'areas' },
]

const store = useSkillsStore()

const search = ref('')
const viewMode = ref<ViewMode>('people')

const allAreas = computed(() => groupByArea(store.profiles))
const people = computed(() => filterProfiles(store.profiles, search.value ?? ''))
const areas = computed(() => filterAreas(allAreas.value, search.value ?? ''))
const shownCount = computed(() => (viewMode.value === 'people' ? people.value.length : areas.value.length))

const countLine = computed(
  () => `${plural(store.profiles.length, 'person', 'people')} · ${plural(allAreas.value.length, 'area')} of code`,
)

onMounted(() => {
  void store.fetchProfiles()
})
</script>

<style scoped>
.skills-search {
  width: 260px;
  flex: 0 1 260px;
}
.skills-loading {
  display: flex;
  justify-content: center;
  padding: 48px 0;
}
.skills-count,
.skills-none {
  margin: 0;
  font-size: 13px;
  color: rgb(var(--v-theme-on-surface-variant));
}
.skills-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(min(100%, 320px), 1fr));
  gap: 16px;
}
@media (max-width: 600px) {
  .skills-search {
    flex-basis: 100%;
    width: 100%;
  }
}
</style>
