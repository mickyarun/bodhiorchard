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
  <v-card class="pa-8 card-border-dark" color="surface">
    <div class="d-flex flex-column align-center text-center mb-6">
      <img :src="logoSrc" width="40" height="40" alt="" class="mb-3" style="border-radius: 50%;" />
      <div class="text-h6 font-weight-medium">Why "Bodhiorchard"?</div>
    </div>

    <div class="story-content mx-auto" style="max-width: 680px;">
      <p class="text-body-1 text-center font-italic text-medium-emphasis mb-6" style="line-height: 1.8;">
        "The purpose of technology is not to keep humans chained to screens, but to set them free."
      </p>

      <p class="text-body-2 text-medium-emphasis mb-4" style="line-height: 1.8;">
        <strong class="text-primary">Bodhi</strong> (Sanskrit: "awakening, enlightenment") is the state
        of understanding that the Buddha attained under the Bodhi tree.
        <strong class="text-primary">Orchard</strong> is a cultivated grove &mdash; trees tended with intention so they can bear fruit.
      </p>

      <p class="text-body-2 text-medium-emphasis mb-4" style="line-height: 1.8;">
        The software industry has a paradox: we build tools to make life better,
        but the process of building them consumes our lives. Developers work late nights.
        PMs spend weekends writing specs. Teams sit through hours of ceremonies &mdash;
        standups, sprint planning, retrospectives, estimation poker &mdash; rituals
        that were meant to help but became the work itself.
      </p>

      <p class="text-body-2 text-medium-emphasis mb-4" style="line-height: 1.8;">
        Bodhiorchard exists because <strong class="text-high-emphasis">AI should give humans their time back</strong>.
        Not to write more code. Not to ship faster. But to reclaim the hours lost to busywork &mdash;
        so a developer can leave at 5pm and take their kid to the park. So a PM can spend their
        morning thinking deeply about what users need instead of copy-pasting tickets. So a team
        lead can mentor junior engineers instead of chasing status updates across five tools.
      </p>

      <p class="text-body-2 text-medium-emphasis mb-4" style="line-height: 1.8;">
        The living tree dashboard isn't just a visualization &mdash; it's the philosophy made visible.
        Your organization is an orchard. Each repository is a tree. Each feature is a branch.
        The AI agents are the orchardists: they water, they prune, they tend the soil. They do the
        repetitive labor so the trees can grow naturally and bear fruit, and the humans who planted them can step
        back, breathe, and enjoy the harvest they've built.
      </p>

      <p class="text-body-2 text-medium-emphasis" style="line-height: 1.8;">
        The Bodhi tree is where awakening happened &mdash; not through more effort, but through
        stillness and clarity. Bodhiorchard is an invitation to build software the same way:
        let the machines handle the noise, so humans can focus on what actually matters.
        <strong class="text-success">Build well. Then go outside.</strong>
      </p>
    </div>
  </v-card>
</template>

<script setup lang="ts">
withDefaults(
  defineProps<{
    logoSrc?: string
  }>(),
  {
    logoSrc: '/assets/bodhiorchard-logo-sm.png',
  },
)
</script>
