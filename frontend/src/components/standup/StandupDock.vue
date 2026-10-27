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

<!-- Holds the standup panel against the viewport's right edge, below any
     top bar, so it stays in view while the page under it scrolls. -->
<template>
  <div class="standup-dock">
    <Transition name="standup-slide">
      <StandupPanel v-if="open" @close="open = false" />
    </Transition>
  </div>
</template>

<script setup lang="ts">
import StandupPanel from './StandupPanel.vue'

const open = defineModel<boolean>({ required: true })
</script>

<style scoped>
.standup-dock {
  position: fixed;
  /* v-main carries the top bar's height in this variable. */
  top: var(--v-layout-top, 0px);
  right: 0;
  bottom: 0;
  width: min(376px, 100%);
  z-index: 20;
  /* The strip never takes clicks; only the panel inside it does. */
  pointer-events: none;
}
.standup-dock > * {
  pointer-events: auto;
}
.standup-slide-enter-active,
.standup-slide-leave-active {
  transition: transform var(--dur-mid) var(--ease-out), opacity var(--dur-mid) var(--ease-out);
}
.standup-slide-enter-from,
.standup-slide-leave-to {
  transform: translateX(40px);
  opacity: 0;
}
</style>
