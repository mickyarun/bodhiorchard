<!-- Copyright 2025-2026 Arun Rajkumar; licensed under Apache-2.0. -->
<template>
  <section class="crowd-panel">
    <div class="crowd-panel__title">
      <h3>{{ viewer ? 'Cheer from the crowd' : 'Encouragement' }}</h3>
      <span><v-icon icon="mdi-eye-outline" size="13" /> {{ viewerCount }} watching</span>
    </div>
    <p>{{ viewer ? 'Send the players a quick reaction.' : 'React to a clever move.' }}</p>
    <div class="crowd-panel__actions">
      <button
        v-for="reaction in BACKLASH_ENCOURAGEMENTS"
        :key="reaction"
        type="button"
        :disabled="disabled"
        :aria-label="`Send ${reaction} encouragement`"
        @click="emit('encourage', reaction)"
      >
        {{ reaction }}
      </button>
    </div>
  </section>
</template>

<script setup lang="ts">
import {
  BACKLASH_ENCOURAGEMENTS,
  type BacklashEncouragement,
} from '@shared/minigames/backlashSocial'

defineProps<{
  viewer: boolean
  viewerCount: number
  disabled: boolean
}>()

const emit = defineEmits<{
  encourage: [reaction: BacklashEncouragement]
}>()
</script>

<style scoped>
.crowd-panel { padding: 15px; border: 1px solid rgba(255,255,255,.09); border-radius: 12px; background: rgba(11,7,5,.55); }
.crowd-panel__title { display: flex; align-items: baseline; justify-content: space-between; gap: 8px; }
.crowd-panel__title h3 { margin: 0; color: #dca064; font-family: Georgia, serif; font-size: 15px; }
.crowd-panel__title span { display: inline-flex; align-items: center; gap: 4px; color: rgba(245,234,211,.42); font-size: 8px; white-space: nowrap; }
.crowd-panel p { margin: 7px 0 9px; color: rgba(245,234,211,.46); font-size: 9px; }
.crowd-panel__actions { display: grid; grid-template-columns: repeat(4, 1fr); gap: 5px; }
.crowd-panel__actions button { border: 1px solid rgba(255,255,255,.1); border-radius: 8px; padding: 7px 3px; background: rgba(255,255,255,.04); font-size: 19px; cursor: pointer; transition: transform .16s, background .16s; }
.crowd-panel__actions button:hover:not(:disabled) { transform: translateY(-2px) scale(1.08); background: rgba(215,131,59,.18); }
.crowd-panel__actions button:disabled { cursor: default; filter: grayscale(.8); opacity: .35; }
</style>
