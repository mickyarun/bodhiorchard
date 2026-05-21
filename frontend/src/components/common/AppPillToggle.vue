<!--
 * Copyright 2025-2026 Arun Rajkumar
 *
 * Licensed under the Apache License, Version 2.0 (the "License");
 * you may not use this file except in compliance with the License.
 -->

<!-- Pill-shaped segmented control.

     Renders a primary-coloured pill track with N options; the
     active option flips to a surface-coloured pill with
     primary-coloured text. Built on a plain ``<button>`` per option
     because Vuetify's ``v-btn-toggle`` paints the active state via
     internal overlays that fight our active-pill-on-track design.

     Usage:
       <AppPillToggle
         v-model="mode"
         :options="[{ label: 'Create', value: 'create' }, ...]"
       />

     v-model is the value of the selected option. ``mandatory`` (the
     default) prevents clicks on the active option from deselecting
     it — useful when the parent assumes a non-null mode at all
     times. -->
<template>
  <div class="app-pill-toggle" :class="`app-pill-toggle--${size}`" role="radiogroup">
    <button
      v-for="opt in options"
      :key="String(opt.value)"
      type="button"
      role="radio"
      class="app-pill-toggle__option"
      :class="{ 'app-pill-toggle__option--active': opt.value === modelValue }"
      :aria-checked="opt.value === modelValue"
      @click="select(opt.value)"
    >
      {{ opt.label }}
    </button>
  </div>
</template>

<script setup lang="ts" generic="T extends string | number">
interface PillOption<V extends string | number> {
  label: string
  value: V
}

interface Props {
  modelValue: T
  options: PillOption<T>[]
  // When true (default), clicking the already-active option does
  // nothing — the parent always sees a non-null model value.
  mandatory?: boolean
  // ``md`` (default) matches the v-tabs density="compact" height
  // (34px). ``sm`` is for tight chrome (e.g. card headers).
  size?: 'sm' | 'md'
}

const props = withDefaults(defineProps<Props>(), {
  mandatory: true,
  size: 'md',
})

const emit = defineEmits<(e: 'update:modelValue', value: T) => void>()

function select(value: T): void {
  if (props.mandatory && value === props.modelValue) return
  emit('update:modelValue', value)
}
</script>

<style scoped>
.app-pill-toggle {
  display: inline-flex;
  align-items: center;
  gap: 2px;
  padding: 3px;
  background: rgb(var(--v-theme-primary));
  border-radius: 999px;
  flex-shrink: 0;
}
.app-pill-toggle--sm {
  height: 28px;
}
.app-pill-toggle--sm .app-pill-toggle__option {
  height: 22px;
  font-size: 11px;
  padding: 0 12px;
  min-width: 64px;
}
.app-pill-toggle--md {
  height: 34px;
}
.app-pill-toggle--md .app-pill-toggle__option {
  height: 28px;
  font-size: 12px;
  padding: 0 18px;
  min-width: 84px;
}
.app-pill-toggle__option {
  /* Reset the user-agent <button> styles, then drive everything from
     here. Without ``color: #fff`` Chrome/Safari fall back to the
     button's default colour (~ButtonText, often near-black) which
     reads as invisible on the primary-green track. */
  appearance: none;
  -webkit-appearance: none;
  border: none;
  background: transparent;
  color: #fff;
  font-family: inherit;
  font-weight: 600;
  letter-spacing: 0;
  text-transform: none;
  border-radius: 999px;
  cursor: pointer;
  transition:
    background-color 0.15s ease,
    color 0.15s ease;
  display: inline-flex;
  align-items: center;
  justify-content: center;
}
.app-pill-toggle__option:hover:not(.app-pill-toggle__option--active) {
  background: rgba(255, 255, 255, 0.18);
}
.app-pill-toggle__option--active {
  background: #fff;
  color: rgb(var(--v-theme-primary));
  cursor: default;
  box-shadow: 0 1px 3px rgba(0, 0, 0, 0.25);
}
.app-pill-toggle__option:focus-visible {
  outline: 2px solid rgba(255, 255, 255, 0.6);
  outline-offset: 2px;
}
</style>
