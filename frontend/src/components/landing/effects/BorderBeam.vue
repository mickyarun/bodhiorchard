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

<!-- A light beam that travels around a rounded border. Pure CSS via an animated
     conic-gradient mask, keyed to the accent token. SSR-safe; the beam stops
     under prefers-reduced-motion. Modeled on the Inspira UI / Magic UI
     "Border Beam" pattern, implemented from scratch. -->
<template>
  <div class="border-beam" aria-hidden="true" />
</template>

<style scoped>
.border-beam {
  position: absolute;
  inset: 0;
  border-radius: inherit;
  padding: 1px;
  pointer-events: none;
  background: conic-gradient(
    from var(--beam-angle, 0deg),
    transparent 0deg,
    rgb(var(--v-theme-primary)) 30deg,
    var(--color-gold, rgb(228, 183, 80)) 60deg,
    transparent 90deg,
    transparent 360deg
  );
  /* Mask leaves only the 1px ring visible. */
  -webkit-mask:
    linear-gradient(#000 0 0) content-box,
    linear-gradient(#000 0 0);
  -webkit-mask-composite: xor;
  mask:
    linear-gradient(#000 0 0) content-box,
    linear-gradient(#000 0 0);
  mask-composite: exclude;
  animation: border-beam-spin 6s linear infinite;
}

@property --beam-angle {
  syntax: '<angle>';
  inherits: false;
  initial-value: 0deg;
}

@keyframes border-beam-spin {
  to { --beam-angle: 360deg; }
}

@media (prefers-reduced-motion: reduce) {
  .border-beam {
    animation: none;
  }
}
</style>
