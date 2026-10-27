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

<!-- Key for the team calendar's chips, and who can see leave types. -->
<template>
  <div class="legend">
    <span class="legend__item"><span class="legend__swatch legend__swatch--leave" />On leave</span>
    <span class="legend__item"><span class="legend__swatch legend__swatch--wfh" />Working from home</span>
    <span class="legend__item"><span class="legend__swatch legend__swatch--pending" />Waiting for approval</span>
    <span class="legend__item"><span class="legend__swatch legend__swatch--holiday" />Holiday</span>
    <span class="legend__item">½ Half day</span>
    <span class="legend__note">Leave types show only to the person, their managers and HR.</span>
  </div>
</template>

<style scoped>
.legend {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 8px 18px;
  font-size: 13px;
  color: rgb(var(--v-theme-ink-2));
}
.legend__item {
  display: inline-flex;
  align-items: center;
  gap: 8px;
}
.legend__swatch {
  width: 22px;
  height: 12px;
  border-radius: 4px;
  box-sizing: border-box;
}
.legend__swatch--leave {
  background: rgba(var(--v-theme-primary), 0.16);
}
.legend__swatch--wfh {
  border: 1.5px solid rgb(var(--v-theme-primary));
}
.legend__swatch--pending {
  border: 1.5px dashed rgb(var(--v-theme-warning));
  background: rgba(var(--v-theme-warning), 0.1);
}
.legend__swatch--holiday {
  background: rgba(var(--v-theme-info), 0.12);
}
.legend__note {
  margin-left: auto;
  color: rgb(var(--v-theme-on-surface-variant));
}
@media (max-width: 900px) {
  .legend__note {
    margin-left: 0;
    flex-basis: 100%;
  }
}
</style>
