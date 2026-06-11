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
  <LandingContainer>
    <div class="py-12 py-md-16">
      <PageHeading
        eyebrow="See it"
        title="The platform"
        lede="The Living Tree, the BUD board, estimation, quality loops, knowledge, and the gamification layer — the surfaces where Agent-Driven Development happens."
        class="mb-12"
      />
      <PlatformScreenshotsSection class="mb-16" />
      <EstimationBudSection class="mb-16" />
      <QualityBacklogSection class="mb-16" />
      <KnowledgeSkillsSection class="mb-16" />
      <GamificationScreenshotsSection class="mb-16" />
      <DemoVideosSection class="mb-16" />
      <FinalCtaBand title="Explore it for yourself" />
    </div>
  </LandingContainer>
</template>

<script setup lang="ts">
import LandingContainer from '../components/LandingContainer.vue'
import PageHeading from '../components/PageHeading.vue'
import FinalCtaBand from '../components/FinalCtaBand.vue'
import PlatformScreenshotsSection from '@/components/methodology/sections/PlatformScreenshotsSection.vue'
import EstimationBudSection from '@/components/methodology/sections/EstimationBudSection.vue'
import QualityBacklogSection from '@/components/methodology/sections/QualityBacklogSection.vue'
import KnowledgeSkillsSection from '@/components/methodology/sections/KnowledgeSkillsSection.vue'
import GamificationScreenshotsSection from '@/components/methodology/sections/GamificationScreenshotsSection.vue'
import DemoVideosSection from '@/components/methodology/sections/DemoVideosSection.vue'
import { useSeo } from '../composables/useSeo'

useSeo({
  title: 'The Platform — Living Tree, BUDs, estimation & more | Bodhiorchard',
  description:
    'A tour of the Bodhiorchard platform: the Living Tree dashboard, the BUD board, AI-PERT estimation, smart quality loops, knowledge that auto-syncs, developer skill profiles, and the gamification layer.',
  path: '/platform',
})
</script>
