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

<!-- Drifting aurora glow for hero backdrops. Pure CSS (no JS, SSR-safe),
     keyed to the Hallmark accent + gold tokens. Animation freezes under
     prefers-reduced-motion. Visual approach inspired by the Inspira UI /
     Aceternity "Aurora Background" pattern; implemented from scratch. -->
<template>
  <div class="aurora" aria-hidden="true">
    <div class="aurora__layer aurora__layer--a" />
    <div class="aurora__layer aurora__layer--b" />
    <div class="aurora__grain" />
  </div>
</template>

<style scoped>
.aurora {
  position: absolute;
  inset: 0;
  overflow: hidden;
  pointer-events: none;
  z-index: 0;
}
.aurora__layer {
  position: absolute;
  inset: -30%;
  filter: blur(60px);
  opacity: 0.55;
  will-change: transform;
}
.aurora__layer--a {
  background:
    radial-gradient(38% 44% at 22% 30%, rgba(62, 171, 94, 0.45), transparent 70%),
    radial-gradient(34% 40% at 78% 24%, rgba(32, 196, 95, 0.30), transparent 72%);
  animation: aurora-drift-a 26s ease-in-out infinite alternate;
}
.aurora__layer--b {
  background:
    radial-gradient(40% 46% at 68% 72%, rgba(228, 183, 80, 0.22), transparent 70%),
    radial-gradient(30% 36% at 30% 80%, rgba(62, 171, 94, 0.28), transparent 72%);
  animation: aurora-drift-b 32s ease-in-out infinite alternate;
}
.aurora__grain {
  position: absolute;
  inset: 0;
  opacity: 0.04;
  background-image: radial-gradient(rgba(255, 255, 255, 0.6) 0.5px, transparent 0.5px);
  background-size: 3px 3px;
}

@keyframes aurora-drift-a {
  from { transform: translate3d(-4%, -2%, 0) scale(1); }
  to   { transform: translate3d(6%, 4%, 0) scale(1.12); }
}
@keyframes aurora-drift-b {
  from { transform: translate3d(3%, 2%, 0) scale(1.08); }
  to   { transform: translate3d(-5%, -3%, 0) scale(1); }
}

@media (prefers-reduced-motion: reduce) {
  .aurora__layer {
    animation: none;
  }
}
</style>
