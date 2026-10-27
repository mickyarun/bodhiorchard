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

<!-- One person's strongest code areas, read from git history. The top
     three show by default; the rest open on request. -->
<template>
  <article class="skill-card">
    <header class="skill-card__head">
      <AppMonogram :name="profile.userName" :size="38" />
      <span class="skill-card__who">
        <span class="skill-card__name">{{ profile.userName }}</span>
        <span class="skill-card__sub">{{ profile.email }}</span>
      </span>
    </header>
    <ul class="skill-card__list">
      <li v-for="mod in shown" :key="mod.name">
        <SkillMeter
          :name="mod.name"
          :score="mod.score"
          :detail="mod.languages.slice(0, 3).join(', ')"
        />
      </li>
    </ul>
    <footer class="skill-card__foot">
      <span>{{ profileSummary(profile.modules) }}</span>
      <v-btn
        v-if="sorted.length > PREVIEW_COUNT"
        variant="text"
        size="small"
        density="comfortable"
        :aria-expanded="expanded"
        @click="expanded = !expanded"
      >
        {{ expanded ? 'Show fewer' : `Show all ${sorted.length}` }}
      </v-btn>
    </footer>
  </article>
</template>

<script setup lang="ts">
import { computed, ref } from 'vue'
import AppMonogram from '@/components/common/AppMonogram.vue'
import SkillMeter from './SkillMeter.vue'
import type { SkillProfile } from '@/types'
import { profileSummary, sortByScore } from '@/utils/skillProfiles'

const PREVIEW_COUNT = 3

const props = defineProps<{ profile: SkillProfile }>()

const expanded = ref(false)
const sorted = computed(() => sortByScore(props.profile.modules))
const shown = computed(() => (expanded.value ? sorted.value : sorted.value.slice(0, PREVIEW_COUNT)))
</script>

<style scoped src="./skillCard.css"></style>
