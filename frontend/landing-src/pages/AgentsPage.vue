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
        eyebrow="The cast"
        title="Meet the twelve agents"
        lede="Each specialised agent owns a phase of the lifecycle — triggered automatically, connected to the others, and always working from the same living knowledge."
        class="mb-12"
      />
      <AgentsSection class="mb-16" />
      <FinalCtaBand title="Put the agents to work" />
    </div>
  </LandingContainer>
</template>

<script setup lang="ts">
import LandingContainer from '../components/LandingContainer.vue'
import PageHeading from '../components/PageHeading.vue'
import FinalCtaBand from '../components/FinalCtaBand.vue'
import AgentsSection from '@/components/methodology/sections/AgentsSection.vue'
import { useSeo } from '../composables/useSeo'

useSeo({
  title: 'The 12 Agents — from triage to learning | Bodhiorchard',
  description:
    'Twelve specialised AI agents orchestrate the software lifecycle in Bodhiorchard: Triage, BUD, Design, Tech Plan, Smart Assignment, Test, Status, Learning, Skill, Bug Linker, Reassignment, and Standup.',
  path: '/agents',
})
</script>
