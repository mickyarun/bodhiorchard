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
        eyebrow="How it works"
        title="The Bodhiorchard methodology"
        lede="From conversation to production — every phase powered by intelligent agents working alongside humans, in a living garden you can watch grow."
        class="mb-12"
      />
      <LifecycleFlowSection class="mb-16" />
      <ManifestoSection class="mb-16" />
      <AiVsHumansSection class="mb-16" />
      <FaqSection class="mb-16" />
      <FinalCtaBand title="See it run on your codebase" />
    </div>
  </LandingContainer>
</template>

<script setup lang="ts">
import LandingContainer from '../components/LandingContainer.vue'
import PageHeading from '../components/PageHeading.vue'
import FaqSection from '../components/FaqSection.vue'
import FinalCtaBand from '../components/FinalCtaBand.vue'
import LifecycleFlowSection from '@/components/methodology/sections/LifecycleFlowSection.vue'
import ManifestoSection from '@/components/methodology/sections/ManifestoSection.vue'
import AiVsHumansSection from '@/components/methodology/sections/AiVsHumansSection.vue'
import { useSeo } from '../composables/useSeo'
import { FAQ_PAGE_LD } from '../seo/structured-data'

useSeo({
  title: 'The Methodology — Agent-Driven Development | Bodhiorchard',
  description:
    'How Agent-Driven Development works: a 9-phase lifecycle where AI agents draft specs, designs, and tests while humans review and steer. The manifesto, the AI-vs-human split, and FAQs.',
  path: '/methodology',
  jsonLd: FAQ_PAGE_LD,
})
</script>
