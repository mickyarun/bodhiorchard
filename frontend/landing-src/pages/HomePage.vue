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
  <div>
    <HomeHero />
    <LandingContainer>
      <div class="py-12 py-md-16">
        <HomeHighlights class="mb-16" />
        <HomeDemo class="mb-16" />
        <VsAgileTeaser class="mb-16" />
        <FinalCtaBand
          title="Ready to plant your first BUD?"
          subtitle="Bodhiorchard is open source and self-hosted. Clone it, bring the stack up locally, and ship your first feature the agent-driven way."
        />
      </div>
    </LandingContainer>
  </div>
</template>

<script setup lang="ts">
import HomeHero from '../components/HomeHero.vue'
import HomeHighlights from '../components/HomeHighlights.vue'
import HomeDemo from '../components/HomeDemo.vue'
import VsAgileTeaser from '../components/VsAgileTeaser.vue'
import FinalCtaBand from '../components/FinalCtaBand.vue'
import LandingContainer from '../components/LandingContainer.vue'
import { useSeo } from '../composables/useSeo'
import { SOFTWARE_APPLICATION_LD } from '../seo/structured-data'

useSeo({
  title: 'Bodhiorchard — Agent-Driven Development · the alternative to sprint, scrum & agile',
  description:
    'Agent-Driven Development replaces sprint, scrum, and agile ceremony with 12 specialised AI agents working alongside humans. Bodhiorchard is the open-source, self-hosted reference implementation. Apache 2.0.',
  path: '/',
  jsonLd: SOFTWARE_APPLICATION_LD,
})
</script>
