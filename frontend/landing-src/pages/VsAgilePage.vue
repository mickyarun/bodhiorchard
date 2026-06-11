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
        eyebrow="The comparison"
        title="Bodhiorchard vs Agile"
        lede="Phase by phase: what sprint, scrum, and agile ask of your team — and what Bodhiorchard automates instead."
        class="mb-12"
      />
      <VsAgileSection class="mb-16" />
      <FinalCtaBand title="Trade ceremony for shipped software" />
    </div>
  </LandingContainer>
</template>

<script setup lang="ts">
import LandingContainer from '../components/LandingContainer.vue'
import PageHeading from '../components/PageHeading.vue'
import FinalCtaBand from '../components/FinalCtaBand.vue'
import VsAgileSection from '@/components/methodology/sections/VsAgileSection.vue'
import { useSeo } from '../composables/useSeo'

useSeo({
  title: 'Bodhiorchard vs Agile — a phase-by-phase comparison',
  description:
    'How Agent-Driven Development compares to Agile / Scrum across 13 phases — from intake and estimation to deployment, knowledge, and retrospectives. The modern alternative to sprint planning and story points.',
  path: '/vs-agile',
})
</script>
