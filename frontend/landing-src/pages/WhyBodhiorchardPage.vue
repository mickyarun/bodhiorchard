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
        eyebrow="The philosophy"
        title="Why &quot;Bodhiorchard&quot;?"
        class="mb-12"
      />
      <WhyBodhiorchardSection :show-heading="false" class="mb-16" />
      <FinalCtaBand title="Build well. Then go outside." ctaLabel="Start on GitHub" />
    </div>
  </LandingContainer>
</template>

<script setup lang="ts">
import LandingContainer from '../components/LandingContainer.vue'
import PageHeading from '../components/PageHeading.vue'
import FinalCtaBand from '../components/FinalCtaBand.vue'
import WhyBodhiorchardSection from '@/components/methodology/sections/WhyBodhiorchardSection.vue'
import { useSeo } from '../composables/useSeo'

useSeo({
  title: 'Why "Bodhiorchard"? — the philosophy',
  description:
    'Bodhi (awakening) + Orchard (a tended grove). Bodhiorchard exists because AI should give humans their time back — let the machines handle the noise so people can focus on what matters. Build well. Then go outside.',
  path: '/why-bodhiorchard',
})
</script>
