<!--
  SPDX-License-Identifier: AGPL-3.0-or-later
  Copyright (C) 2026 Arun Rajkumar

  Compact action menu for a single repository row.

  Built on a plain v-menu + native <button> markup instead of v-list /
  v-list-item, because Vuetify's list-item internals reserve a fixed
  prepend column that fights every attempt to reduce the icon-to-text
  gap. This component owns the menu items as a typed array so the
  parent only wires emits.
-->
<template>
  <v-menu location="bottom end" :close-on-content-click="true">
    <template #activator="{ props: menu }">
      <v-btn
        v-bind="menu"
        icon="mdi-dots-vertical"
        size="small"
        variant="text"
        density="compact"
        :disabled="disabled"
      />
    </template>

    <div class="row-menu" role="menu">
      <button
        v-for="item in items"
        :key="item.id"
        type="button"
        role="menuitem"
        class="row-menu-item"
        :class="{ 'is-danger': item.danger }"
        @click="onClick(item.id)"
      >
        <v-icon :icon="item.icon" size="16" class="row-menu-icon" />
        <span class="row-menu-label">{{ item.label }}</span>
      </button>
    </div>
  </v-menu>
</template>

<script setup lang="ts">
import { computed } from 'vue'

export type RepoRowMenuId = 'edit-branches' | 'toggle-status' | 'remove'

interface MenuItem {
  id: RepoRowMenuId
  icon: string
  label: string
  danger?: boolean
}

const props = defineProps<{
  status: string
  disabled?: boolean
}>()

const emit = defineEmits<{
  select: [id: RepoRowMenuId]
}>()

const items = computed<MenuItem[]>(() => [
  { id: 'edit-branches', icon: 'mdi-pencil-outline', label: 'Edit branches' },
  {
    id: 'toggle-status',
    icon: props.status === 'active' ? 'mdi-eye-off-outline' : 'mdi-eye-outline',
    label: props.status === 'active' ? 'Ignore' : 'Activate',
  },
  { id: 'remove', icon: 'mdi-delete-outline', label: 'Remove', danger: true },
])

function onClick(id: RepoRowMenuId): void {
  emit('select', id)
}
</script>

<style scoped>
.row-menu {
  display: flex;
  flex-direction: column;
  min-width: 156px;
  padding: 4px;
  background: rgb(var(--v-theme-surface));
  border: 1px solid rgba(var(--v-theme-on-surface), 0.08);
  border-radius: 6px;
  box-shadow: 0 6px 20px rgba(0, 0, 0, 0.35);
}

.row-menu-item {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 6px 10px;
  border-radius: 4px;
  background: transparent;
  border: 0;
  color: rgb(var(--v-theme-on-surface));
  font-size: 13px;
  line-height: 1;
  text-align: left;
  cursor: pointer;
  transition: background-color 0.12s ease;
}

.row-menu-item:hover {
  background: rgba(var(--v-theme-on-surface), 0.06);
}

.row-menu-item.is-danger {
  color: rgb(var(--v-theme-error));
}

.row-menu-icon {
  flex-shrink: 0;
  opacity: 0.85;
}

.row-menu-label {
  flex: 1;
}
</style>
