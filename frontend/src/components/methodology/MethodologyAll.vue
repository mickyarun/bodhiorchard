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

<!-- Recomposes every methodology section into one continuous scroll, in the
     original order. The in-app /methodology route renders this directly; the
     public landing site distributes the same section components across routes. -->
<template>
  <div class="methodology-page">
    <HeroSection
      @start-building="emit('startBuilding')"
      @watch-tour="scrollToTour"
    />

    <div ref="tourSection" class="mb-10">
      <DemoVideosSection />
    </div>

    <PlatformScreenshotsSection class="mb-8" />
    <GamificationScreenshotsSection class="mb-10" />
    <LifecycleFlowSection class="mb-8" />
    <ManifestoSection class="mb-8" />
    <AgentsSection class="mb-8" />
    <AiVsHumansSection class="mb-8" />
    <EstimationBudSection class="mb-8" />
    <QualityBacklogSection class="mb-8" />
    <KnowledgeSkillsSection class="mb-8" />
    <VsAgileSection class="mb-8" />
    <WhyBodhiorchardSection class="mb-8" />
    <FinalCtaSection @start-building="emit('startBuilding')" />
  </div>
</template>

<script setup lang="ts">
import { ref } from 'vue'
import HeroSection from '@/components/methodology/sections/HeroSection.vue'
import DemoVideosSection from '@/components/methodology/sections/DemoVideosSection.vue'
import PlatformScreenshotsSection from '@/components/methodology/sections/PlatformScreenshotsSection.vue'
import GamificationScreenshotsSection from '@/components/methodology/sections/GamificationScreenshotsSection.vue'
import LifecycleFlowSection from '@/components/methodology/sections/LifecycleFlowSection.vue'
import ManifestoSection from '@/components/methodology/sections/ManifestoSection.vue'
import AgentsSection from '@/components/methodology/sections/AgentsSection.vue'
import AiVsHumansSection from '@/components/methodology/sections/AiVsHumansSection.vue'
import EstimationBudSection from '@/components/methodology/sections/EstimationBudSection.vue'
import QualityBacklogSection from '@/components/methodology/sections/QualityBacklogSection.vue'
import KnowledgeSkillsSection from '@/components/methodology/sections/KnowledgeSkillsSection.vue'
import VsAgileSection from '@/components/methodology/sections/VsAgileSection.vue'
import WhyBodhiorchardSection from '@/components/methodology/sections/WhyBodhiorchardSection.vue'
import FinalCtaSection from '@/components/methodology/sections/FinalCtaSection.vue'

const emit = defineEmits<{
  startBuilding: []
}>()

const tourSection = ref<HTMLElement | null>(null)
function scrollToTour(): void {
  tourSection.value?.scrollIntoView({ behavior: 'smooth', block: 'start' })
}
</script>
