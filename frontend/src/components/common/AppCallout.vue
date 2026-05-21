<!--
 * Copyright 2025-2026 Arun Rajkumar
 *
 * Licensed under the Apache License, Version 2.0 (the "License");
 * you may not use this file except in compliance with the License.
 -->

<!-- Inline informational callout.

     The project's preferred replacement for Vuetify ``v-alert``
     where the alert is a passive note (not a dismissible toast).
     ``v-alert`` paints a saturated tonal fill across the whole row
     which fights the dark chrome; this component uses a muted
     surface tint + a 3px left accent bar + a hairline border on
     the remaining sides + an eyebrow label + optional icon slot,
     so the callout reads as a hint rather than a warning siren.

     Variants:
       * ``info``    — primary accent. Informational notes.
       * ``warning`` — warning accent. Risk / security hints.
       * ``success`` — success accent. Confirmation / status.

     Usage:
       <AppCallout variant="info" eyebrow="Writes are bounded" icon="mdi-shield-check-outline">
         Body content goes here.
       </AppCallout>

     Omit the eyebrow for a compact form (body + accent only). The
     icon defaults to a sensible mdi-* per variant. -->
<template>
  <div class="app-callout" :class="`app-callout--${variant}`">
    <div v-if="resolvedIcon" class="app-callout__icon">
      <v-icon :icon="resolvedIcon" size="18" />
    </div>
    <div class="app-callout__body">
      <div v-if="eyebrow" class="app-callout__eyebrow">{{ eyebrow }}</div>
      <div v-if="title" class="app-callout__title">{{ title }}</div>
      <div class="app-callout__text">
        <slot />
      </div>
    </div>
    <div v-if="$slots.actions" class="app-callout__actions">
      <slot name="actions" />
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'

type Variant = 'info' | 'warning' | 'success'

interface Props {
  variant?: Variant
  eyebrow?: string
  // Optional bolder line between eyebrow and body. Use when the
  // callout needs a "headline" feel (e.g. a banner) rather than a
  // simple inline note.
  title?: string
  // ``mdi-*`` name. Omit to use the variant default; pass ``null``
  // explicitly to render with no icon column.
  icon?: string | null
}

const props = withDefaults(defineProps<Props>(), {
  variant: 'info',
  eyebrow: '',
  title: '',
  icon: undefined,
})

const DEFAULT_ICON: Record<Variant, string> = {
  info: 'mdi-information-outline',
  warning: 'mdi-alert-outline',
  success: 'mdi-check-circle-outline',
}

const resolvedIcon = computed<string | null>(() => {
  if (props.icon === null) return null
  return props.icon || DEFAULT_ICON[props.variant]
})
</script>

<style scoped>
.app-callout {
  display: grid;
  grid-template-columns: auto 1fr auto;
  align-items: start;
  gap: 12px;
  padding: 12px 14px;
  border-radius: 10px;
  border: 1px solid rgba(var(--v-theme-on-surface), 0.08);
  background: rgba(var(--v-theme-on-surface), 0.025);
  border-left-width: 3px;
}
.app-callout:has(.app-callout__body:only-child) {
  grid-template-columns: 1fr;
}
.app-callout__actions {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-shrink: 0;
}
.app-callout__title {
  font-size: 14px;
  font-weight: 600;
  color: rgba(var(--v-theme-on-surface), 0.92);
  line-height: 1.4;
  margin-top: 1px;
}

@media (max-width: 720px) {
  .app-callout {
    grid-template-columns: auto 1fr;
  }
  .app-callout__actions {
    grid-column: 1 / -1;
    justify-content: flex-end;
    padding-top: 4px;
  }
}
.app-callout__icon {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 28px;
  height: 28px;
  border-radius: 6px;
}
.app-callout__body {
  min-width: 0;
}
.app-callout__eyebrow {
  font-size: 10px;
  font-weight: 600;
  letter-spacing: 0.08em;
  text-transform: uppercase;
  margin-bottom: 2px;
}
.app-callout__text {
  font-size: 12.5px;
  line-height: 1.55;
  color: rgba(var(--v-theme-on-surface), 0.78);
}

.app-callout--info {
  background: rgba(var(--v-theme-primary), 0.035);
  border-left-color: rgb(var(--v-theme-primary));
}
.app-callout--info .app-callout__icon {
  background: rgba(var(--v-theme-primary), 0.1);
  color: rgb(var(--v-theme-primary));
}
.app-callout--info .app-callout__eyebrow {
  color: rgb(var(--v-theme-primary));
}

.app-callout--warning {
  background: rgba(var(--v-theme-warning), 0.04);
  border-left-color: rgb(var(--v-theme-warning));
}
.app-callout--warning .app-callout__icon {
  background: rgba(var(--v-theme-warning), 0.12);
  color: rgb(var(--v-theme-warning));
}
.app-callout--warning .app-callout__eyebrow {
  color: rgb(var(--v-theme-warning));
}

.app-callout--success {
  background: rgba(var(--v-theme-success), 0.04);
  border-left-color: rgb(var(--v-theme-success));
}
.app-callout--success .app-callout__icon {
  background: rgba(var(--v-theme-success), 0.12);
  color: rgb(var(--v-theme-success));
}
.app-callout--success .app-callout__eyebrow {
  color: rgb(var(--v-theme-success));
}
</style>
