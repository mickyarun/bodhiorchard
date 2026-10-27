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

<!-- One code area and the people who know it, strongest first. An area
     only one person has touched is flagged: if they are away, nobody
     else has context. -->
<template>
  <article class="skill-card">
    <header class="skill-card__head">
      <span class="skill-card__icon" aria-hidden="true"><v-icon icon="mdi-folder-outline" size="20" /></span>
      <span class="skill-card__who">
        <span class="skill-card__name">{{ area.name }}</span>
        <span class="skill-card__sub">{{ area.languages.slice(0, 4).join(', ') || 'No language detected' }}</span>
      </span>
      <AppTag v-if="area.people.length === 1" color="warning" sr-prefix="Risk:">One person</AppTag>
    </header>
    <ul class="skill-card__list">
      <li v-for="(person, i) in shown" :key="person.email">
        <SkillMeter
          :name="person.userName"
          :score="person.score"
          :color="rankColour(i)"
          :detail="plural(person.touchCount, 'commit')"
        />
      </li>
    </ul>
    <footer class="skill-card__foot">
      <span>{{ plural(area.people.length, 'person', 'people') }}</span>
      <v-btn
        v-if="area.people.length > PREVIEW_COUNT"
        variant="text"
        size="small"
        density="comfortable"
        :aria-expanded="expanded"
        @click="expanded = !expanded"
      >
        {{ expanded ? 'Show fewer' : `Show all ${area.people.length}` }}
      </v-btn>
    </footer>
  </article>
</template>

<script setup lang="ts">
import { computed, ref } from 'vue'
import AppTag from '@/components/common/AppTag.vue'
import SkillMeter from './SkillMeter.vue'
import { plural, rankColour, type SkillArea } from '@/utils/skillProfiles'

const PREVIEW_COUNT = 3

const props = defineProps<{ area: SkillArea }>()

const expanded = ref(false)
const shown = computed(() => (expanded.value ? props.area.people : props.area.people.slice(0, PREVIEW_COUNT)))
</script>

<style scoped src="./skillCard.css"></style>
