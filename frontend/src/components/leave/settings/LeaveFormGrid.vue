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

<!-- Two-column field layout for the leave settings forms; one column on
     narrow screens. Give a child the `span-2` class to take a full row. -->
<template>
  <div class="leave-form-grid">
    <slot />
  </div>
</template>

<style scoped>
.leave-form-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 20px 16px;
  max-width: 720px;
}
.leave-form-grid > :slotted(.span-2) {
  grid-column: 1 / -1;
}
@media (max-width: 600px) {
  .leave-form-grid {
    grid-template-columns: minmax(0, 1fr);
  }
}
</style>
