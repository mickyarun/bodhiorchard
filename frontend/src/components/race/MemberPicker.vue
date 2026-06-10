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

<!-- Multi-select list of org members used by both RaceSetupDialog and
     RaceInviteMoreDialog. The caller owns the directory fetch and any
     domain-specific filtering (exclude-self, exclude-already-invited,
     etc.) — this component is purely the picker UI plus selection state
     forwarding via v-model. -->
<template>
  <div class="member-picker">
    <div v-if="loading" class="d-flex justify-center pa-6">
      <v-progress-circular indeterminate size="28" color="primary" />
    </div>

    <div v-else-if="members.length === 0" class="member-picker__empty">
      {{ emptyMessage }}
    </div>

    <ul v-else class="member-picker__list">
      <li v-for="m in members" :key="m.id">
        <button
          type="button"
          class="member-picker__item"
          :class="{
            'member-picker__item--selected': isSelected(m.id),
            'member-picker__item--disabled': isCapped(m.id),
          }"
          :disabled="isCapped(m.id)"
          @click="toggle(m.id)"
        >
          <span class="member-picker__avatar">{{ initials(m.name) }}</span>
          <span class="member-picker__text">
            <span class="member-picker__name">{{ m.name }}</span>
            <span class="member-picker__email">{{ m.email }}</span>
          </span>
          <span
            class="member-picker__check"
            :class="{ 'member-picker__check--on': isSelected(m.id) }"
          >
            <v-icon v-if="isSelected(m.id)" icon="mdi-check" size="14" />
          </span>
        </button>
      </li>
    </ul>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { initials } from './initials'

export interface MemberPickerEntry {
  id: string
  name: string
  email: string
}

const props = withDefaults(
  defineProps<{
    members: MemberPickerEntry[]
    /**
     * Selected ids. **Caller invariant:** length must be
     * ``<= maxSelection`` on the initial render — the picker does not
     * clamp an oversized incoming array. ``toggle()`` itself enforces
     * the cap so the user can never push past it, but a parent that
     * forces an oversized value silently lets the user only de-select
     * until they're back under the cap.
     */
    modelValue: string[]
    /** Maximum number of entries the user may select. */
    maxSelection: number
    loading?: boolean
    /** Shown when ``members`` is empty after loading. */
    emptyMessage?: string
  }>(),
  {
    loading: false,
    emptyMessage: 'No members available.',
  },
)

const emit = defineEmits<{
  (e: 'update:modelValue', ids: string[]): void
}>()

const atCap = computed(() => props.modelValue.length >= props.maxSelection)

function isSelected(id: string): boolean {
  return props.modelValue.includes(id)
}

function isCapped(id: string): boolean {
  return atCap.value && !isSelected(id)
}

function toggle(id: string): void {
  const next = [...props.modelValue]
  const i = next.indexOf(id)
  if (i >= 0) {
    next.splice(i, 1)
  } else if (next.length < props.maxSelection) {
    next.push(id)
  }
  emit('update:modelValue', next)
}
</script>

<style scoped>
.member-picker__empty {
  text-align: center;
  padding: 24px;
  color: rgba(255, 255, 255, 0.55);
  font-size: 13px;
}
.member-picker__list {
  list-style: none;
  padding: 0;
  margin: 0;
  display: flex;
  flex-direction: column;
  gap: 4px;
}
.member-picker__item {
  width: 100%;
  display: grid;
  grid-template-columns: 32px 1fr 24px;
  align-items: center;
  gap: 12px;
  padding: 8px 12px;
  border: 1px solid transparent;
  border-radius: 8px;
  background: transparent;
  color: inherit;
  font-family: inherit;
  text-align: left;
  cursor: pointer;
  transition: background 0.12s, border-color 0.12s;
}
.member-picker__item:hover:not(.member-picker__item--disabled) {
  background: rgba(255, 255, 255, 0.05);
}
.member-picker__item--selected {
  background: rgba(125, 213, 125, 0.08);
  border-color: rgba(125, 213, 125, 0.3);
}
.member-picker__item--disabled {
  opacity: 0.35;
  cursor: not-allowed;
}
.member-picker__avatar {
  width: 32px;
  height: 32px;
  border-radius: 50%;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  font-size: 11px;
  font-weight: 700;
  background: linear-gradient(135deg, #4b7bb0, #2d5680);
  color: #fff;
  letter-spacing: 0.02em;
}
.member-picker__item--selected .member-picker__avatar {
  background: linear-gradient(135deg, #7dd57d, #5bae5b);
  color: #06130b;
}
.member-picker__text {
  display: flex;
  flex-direction: column;
  min-width: 0;
}
.member-picker__name {
  font-size: 14px;
  font-weight: 600;
  overflow: hidden;
  white-space: nowrap;
  text-overflow: ellipsis;
}
.member-picker__email {
  font-size: 11px;
  color: rgba(255, 255, 255, 0.45);
  overflow: hidden;
  white-space: nowrap;
  text-overflow: ellipsis;
  margin-top: 1px;
}
.member-picker__check {
  width: 22px;
  height: 22px;
  border-radius: 6px;
  border: 1.5px solid rgba(255, 255, 255, 0.2);
  display: inline-flex;
  align-items: center;
  justify-content: center;
  transition: background 0.15s, border-color 0.15s;
}
.member-picker__check--on {
  background: linear-gradient(135deg, #30d66d, #19a34f);
  border-color: transparent;
  color: #fff;
  box-shadow: 0 4px 12px rgba(47, 216, 107, 0.3);
}
</style>
