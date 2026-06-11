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

<!-- Animated gradient text fill (background-clip:text). Pure CSS, SSR-safe.
     The gradient sweeps across the Hallmark accent → gold ramp; the sweep
     stops under prefers-reduced-motion (gradient stays, motion removed). -->
<template>
  <span class="gradient-text"><slot /></span>
</template>

<style scoped>
.gradient-text {
  background: linear-gradient(
    100deg,
    rgb(var(--v-theme-primary)) 0%,
    var(--color-focus, rgb(32, 196, 95)) 35%,
    var(--color-gold, rgb(228, 183, 80)) 65%,
    rgb(var(--v-theme-primary)) 100%
  );
  background-size: 250% 100%;
  -webkit-background-clip: text;
  background-clip: text;
  color: transparent;
  -webkit-text-fill-color: transparent;
  animation: gradient-text-sweep 8s linear infinite;
}

@keyframes gradient-text-sweep {
  to { background-position: 250% 0; }
}

@media (prefers-reduced-motion: reduce) {
  .gradient-text {
    animation: none;
    background-position: 0 0;
  }
}
</style>
