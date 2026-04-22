<!-- SPDX-License-Identifier: AGPL-3.0-or-later -->
<!-- Copyright (C) 2026 Arun Rajkumar -->
<!--
  CheckerFlagIcon — pure CSS 2×2 checkered-flag chip used across race
  surfaces (invite eyebrow, setup dialog, lobby, results). Uses the
  same four-gradient trick everywhere; extracted so palette/size tweaks
  only happen in one place.
-->
<template>
  <span
    class="checker-flag"
    :style="{ width: `${size}px`, height: `${size}px` }"
    aria-hidden="true"
  />
</template>

<script setup lang="ts">
withDefaults(
  defineProps<{
    /** Edge length in pixels. Defaults to 14 — lobby/results size. */
    size?: number
  }>(),
  { size: 14 },
)
</script>

<style scoped>
.checker-flag {
  display: inline-block;
  border-radius: 2px;
  background-image:
    linear-gradient(45deg, #fff 25%, transparent 25%),
    linear-gradient(-45deg, #fff 25%, transparent 25%),
    linear-gradient(45deg, transparent 75%, #fff 75%),
    linear-gradient(-45deg, transparent 75%, #fff 75%);
  /* Half-tile so we get a 2×2 pattern regardless of size. */
  background-size: calc(50% - 1px) calc(50% - 1px);
  background-position: 0 0, 0 100%, 100% 0, 100% 100%;
  background-repeat: no-repeat;
  background-color: #111;
}
</style>
