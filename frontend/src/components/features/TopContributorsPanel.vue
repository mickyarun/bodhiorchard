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
  <div v-if="contributors.length > 0 || loading" class="contrib-strip">
    <div class="contrib-strip__head">
      <v-icon icon="mdi-account-group-outline" size="16" color="primary" />
      <span class="contrib-strip__title">Top contributors</span>
    </div>
    <div v-if="loading && contributors.length === 0" class="contrib-strip__loading">
      <v-progress-circular indeterminate size="18" width="2" color="primary" />
    </div>
    <ol v-else class="contrib-strip__list">
      <li
        v-for="(c, i) in contributors"
        :key="(c.userId ?? c.actorName) + '-' + i"
        class="contrib-row"
      >
        <v-avatar :color="avatarColor(c.actorName)" size="28" class="contrib-row__avatar">
          <span>{{ initials(c.actorName) }}</span>
        </v-avatar>
        <div class="contrib-row__body">
          <div class="contrib-row__name">{{ c.actorName }}</div>
          <div class="contrib-row__stats">
            {{ c.commitCount }} commit{{ c.commitCount === 1 ? '' : 's' }}
            <span class="contrib-row__dot">·</span>
            {{ c.filesChanged }} file{{ c.filesChanged === 1 ? '' : 's' }}
          </div>
        </div>
      </li>
    </ol>
  </div>
</template>

<script setup lang="ts">
import type { RepoContributor } from '@/types'

defineProps<{
  contributors: RepoContributor[]
  loading: boolean
}>()

function initials(name: string): string {
  const parts = name.trim().split(/\s+/).filter(Boolean)
  if (parts.length === 0) return '?'
  if (parts.length === 1) return parts[0].slice(0, 2).toUpperCase()
  return (parts[0][0] + parts[parts.length - 1][0]).toUpperCase()
}

const palette = ['primary', 'success', 'warning', 'info', 'cyan', 'teal', 'deep-purple']

function avatarColor(name: string): string {
  let hash = 0
  for (let i = 0; i < name.length; i++) hash = (hash * 31 + name.charCodeAt(i)) & 0x7fffffff
  return palette[hash % palette.length]
}
</script>

<style scoped>
.contrib-strip {
  display: flex;
  align-items: center;
  gap: 18px;
  padding: 12px 16px;
  border-radius: 10px;
  background: rgba(0, 0, 0, 0.18);
  border: 1px solid rgba(255, 255, 255, 0.06);
  flex-wrap: wrap;
  margin-bottom: 18px;
}
.contrib-strip__head {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 0.72rem;
  text-transform: uppercase;
  letter-spacing: 0.06em;
  color: rgba(255, 255, 255, 0.65);
  font-weight: 600;
  flex-shrink: 0;
}
.contrib-strip__loading {
  display: flex;
  align-items: center;
}
.contrib-strip__list {
  list-style: none;
  margin: 0;
  padding: 0;
  display: flex;
  flex-wrap: wrap;
  gap: 18px;
}
.contrib-row {
  display: flex;
  align-items: center;
  gap: 8px;
}
.contrib-row__avatar {
  font-size: 0.72rem !important;
  font-weight: 700;
}
.contrib-row__body {
  display: flex;
  flex-direction: column;
  min-width: 0;
}
.contrib-row__name {
  font-size: 0.82rem;
  color: rgba(255, 255, 255, 0.92);
  font-weight: 500;
  line-height: 1.2;
}
.contrib-row__stats {
  font-size: 0.7rem;
  color: rgba(255, 255, 255, 0.5);
  line-height: 1.2;
}
.contrib-row__dot {
  margin: 0 4px;
}
</style>
