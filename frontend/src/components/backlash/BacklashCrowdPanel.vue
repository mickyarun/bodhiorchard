<!--
  Copyright 2025-2026 Arun Rajkumar

  Licensed under the Apache License, Version 2.0 (the "License");
  you may not use this file except in compliance with the License.
  You may obtain a copy of the License at

      http://www.apache.org/licenses/LICENSE-2.0

  Unless required by applicable law or agreed to in writing, software
  distributed under the License is distributed on an "AS IS" BASIS,
  WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
  See the License for the specific language governing permissions and
  limitations under the License.
-->
<template>
  <section class="crowd-panel">
    <div class="crowd-panel__title">
      <h3>{{ viewer ? 'Cheer from the crowd' : 'Encouragement' }}</h3>
      <span><v-icon icon="mdi-eye-outline" size="13" /> {{ viewerCount }} watching</span>
    </div>
    <p>{{ viewer ? 'Send the players a quick reaction.' : 'React to a clever move.' }}</p>
    <div v-if="viewers.length" class="crowd-panel__watchers" aria-label="People watching">
      <span v-for="(watcher, index) in viewers" :key="`${watcher.userId}-${index}`">
        <i>{{ initials(watcher.name) }}</i>{{ watcher.name }}
      </span>
    </div>
    <div v-else class="crowd-panel__empty">No one is watching yet</div>
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
import type { BacklashViewerSnapshot } from '@/multiplayer/BacklashRoomClient'

defineProps<{
  viewer: boolean
  viewerCount: number
  viewers: readonly BacklashViewerSnapshot[]
  disabled: boolean
}>()

const emit = defineEmits<{
  encourage: [reaction: BacklashEncouragement]
}>()

function initials(name: string): string {
  return name.trim().split(/\s+/).slice(0, 2).map((part) => part[0]?.toUpperCase()).join('') || '?'
}
</script>

<style scoped>
.crowd-panel { padding: 15px; border: 1px solid rgba(255,255,255,.09); border-radius: 12px; background: rgba(11,7,5,.55); }
.crowd-panel__title { display: flex; align-items: baseline; justify-content: space-between; gap: 8px; }
.crowd-panel__title h3 { margin: 0; color: #dca064; font-family: Georgia, serif; font-size: 15px; }
.crowd-panel__title span { display: inline-flex; align-items: center; gap: 4px; color: rgba(245,234,211,.42); font-size: 8px; white-space: nowrap; }
.crowd-panel p { margin: 7px 0 9px; color: rgba(245,234,211,.46); font-size: 9px; }
.crowd-panel__watchers { display: flex; flex-wrap: wrap; gap: 5px; max-height: 72px; margin-bottom: 10px; overflow-y: auto; }
.crowd-panel__watchers span { display: inline-flex; align-items: center; gap: 5px; min-width: 0; max-width: 100%; border: 1px solid rgba(231,174,113,.16); border-radius: 999px; padding: 3px 7px 3px 3px; background: rgba(231,174,113,.07); color: rgba(255,241,219,.7); font-size: 8px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.crowd-panel__watchers i { display: grid; place-items: center; flex: 0 0 20px; width: 20px; height: 20px; border-radius: 50%; background: rgba(220,160,100,.2); color: #efbd89; font-style: normal; font-size: 7px; font-weight: 900; }
.crowd-panel__empty { margin-bottom: 10px; color: rgba(245,234,211,.3); font-size: 8px; }
.crowd-panel__actions { display: grid; grid-template-columns: repeat(4, 1fr); gap: 5px; }
.crowd-panel__actions button { border: 1px solid rgba(255,255,255,.1); border-radius: 8px; padding: 7px 3px; background: rgba(255,255,255,.04); font-size: 19px; cursor: pointer; transition: transform .16s, background .16s; }
.crowd-panel__actions button:hover:not(:disabled) { transform: translateY(-2px) scale(1.08); background: rgba(215,131,59,.18); }
.crowd-panel__actions button:disabled { cursor: default; filter: grayscale(.8); opacity: .35; }
</style>
