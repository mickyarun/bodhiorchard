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

<!-- Group title inside the sidebar. In rail mode there is no room for a
     label, so the group is separated by a hairline instead. -->
<template>
  <v-list-subheader v-if="!rail" class="nav-heading">{{ label }}</v-list-subheader>
  <v-divider v-else class="my-2" />
</template>

<script setup lang="ts">
defineProps<{ label: string; rail: boolean }>()
</script>

<style scoped>
.nav-heading {
  font-size: 11px;
  font-weight: 600;
  letter-spacing: var(--tracking-label);
  text-transform: uppercase;
  color: rgb(var(--v-theme-muted));
  min-height: 28px;
  margin-top: 12px;
}
</style>
