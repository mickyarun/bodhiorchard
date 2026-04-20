<!-- SPDX-License-Identifier: AGPL-3.0-or-later -->
<!-- Copyright (C) 2026 Arun Rajkumar -->
<!--
  RaceThemeBackdrop — the diagonal speed-stripes + radial amber glow used
  behind every race-flow surface (invite toast, setup dialog, lobby,
  results card). Extracted so all four surfaces share one source of
  truth for the theme.

  Usage:
      <RaceThemeBackdrop />           // default: full-surface backdrop
      <RaceThemeBackdrop variant="narrow" />  // tighter glow for toasts
      <RaceThemeBackdrop :stripes="false" />  // glow only
-->
<template>
  <div class="race-theme-backdrop" :class="`race-theme-backdrop--${variant}`" aria-hidden="true">
    <div v-if="stripes" class="race-theme-backdrop__stripes" />
    <div class="race-theme-backdrop__glow" />
  </div>
</template>

<script setup lang="ts">
withDefaults(
  defineProps<{
    /** 'wide' = full-surface (lobby/results), 'narrow' = toast-sized. */
    variant?: 'wide' | 'narrow'
    /** Show the diagonal stripes? Some surfaces only want the glow. */
    stripes?: boolean
  }>(),
  { variant: 'wide', stripes: true },
)
</script>

<style scoped>
.race-theme-backdrop {
  position: absolute;
  inset: 0;
  z-index: 0;
  pointer-events: none;
  overflow: hidden;
}

.race-theme-backdrop__stripes {
  position: absolute;
  inset: -40px;
  background: repeating-linear-gradient(
    115deg,
    transparent 0 60px,
    rgba(255, 255, 255, 0.022) 60px 61px,
    transparent 61px 120px,
    rgba(255, 193, 7, 0.03) 120px 121px
  );
}

.race-theme-backdrop--wide .race-theme-backdrop__stripes {
  mask-image: radial-gradient(ellipse 100% 90% at 50% 20%, black 40%, transparent 100%);
}
.race-theme-backdrop--narrow .race-theme-backdrop__stripes {
  mask-image: radial-gradient(ellipse 100% 120% at 20% 50%, black 55%, transparent 100%);
}

.race-theme-backdrop__glow {
  position: absolute;
  background: radial-gradient(ellipse, rgba(255, 193, 7, 0.12), transparent 60%);
  filter: blur(40px);
}

.race-theme-backdrop--wide .race-theme-backdrop__glow {
  top: -10%;
  left: 50%;
  transform: translateX(-50%);
  width: 90%;
  height: 70%;
}

.race-theme-backdrop--narrow .race-theme-backdrop__glow {
  top: -30%;
  left: -10%;
  width: 60%;
  height: 140%;
  filter: blur(30px);
}
</style>
