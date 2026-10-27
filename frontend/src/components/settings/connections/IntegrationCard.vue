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

<!-- One integration on Settings → Integrations: icon, name, status tag,
     what it does and one action. The action opens the settings below;
     they stay mounted while closed so status checks keep running. -->
<template>
  <section class="integration" :aria-labelledby="titleId">
    <div class="integration__row">
      <span class="integration__icon" aria-hidden="true"><v-icon :icon="icon" size="22" /></span>
      <div class="integration__text">
        <span class="integration__name">
          <h3 :id="titleId">{{ name }}</h3>
          <AppTag v-if="status.label" :color="status.color" sr-prefix="Status:">{{ status.label }}</AppTag>
        </span>
        <span class="integration__body">{{ description }}</span>
      </div>
      <v-btn
        :color="primary ? 'primary' : undefined"
        :variant="primary ? 'flat' : 'outlined'"
        :aria-expanded="open"
        :aria-controls="panelId"
        class="integration__action"
        @click="open = !open"
      >
        {{ integrationActionLabel(open, status.connected, connectLabel) }}
      </v-btn>
    </div>
    <v-expand-transition>
      <div v-show="open" :id="panelId" class="integration__panel">
        <slot />
      </div>
    </v-expand-transition>
  </section>
</template>

<script setup lang="ts">
import { useId } from 'vue'
import AppTag from '@/components/common/AppTag.vue'
import { integrationActionLabel, type IntegrationStatus } from '@/utils/integrations'

defineProps<{
  name: string
  description: string
  icon: string
  status: IntegrationStatus
  /** The button text while not connected, e.g. "Connect Slack". */
  connectLabel: string
  primary?: boolean
}>()

const open = defineModel<boolean>('open', { required: true })
const titleId = useId()
const panelId = useId()
</script>

<style scoped>
.integration {
  border: 1px solid rgb(var(--v-theme-rule));
  border-radius: 12px;
  background: rgb(var(--v-theme-surface));
  min-width: 0;
}
.integration__row {
  display: flex;
  align-items: center;
  gap: 16px;
  padding: 18px 20px;
}
.integration__icon {
  width: 44px;
  height: 44px;
  flex-shrink: 0;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  border-radius: 10px;
  color: rgb(var(--v-theme-ink-2));
  background: rgb(var(--v-theme-surface-variant));
}
.integration__text {
  display: flex;
  flex-direction: column;
  gap: 3px;
  flex: 1 1 200px;
  min-width: 0;
}
.integration__name {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 4px 10px;
}
.integration__name h3 {
  margin: 0;
  font-size: 15px;
  font-weight: 600;
}
.integration__body {
  font-size: 13px;
  line-height: 19px;
  color: rgb(var(--v-theme-ink-2));
}
.integration__action {
  flex-shrink: 0;
}
.integration__panel {
  padding: 4px 20px 20px;
  border-top: 1px solid var(--color-rule-2);
}
.integration__panel > :first-child {
  margin-top: 16px;
}
@media (max-width: 600px) {
  .integration__row {
    flex-wrap: wrap;
    padding: 16px;
  }
  .integration__action {
    width: 100%;
  }
  .integration__panel {
    padding: 4px 16px 16px;
  }
}
</style>
