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

<!-- Cards in two columns when there is room, one when there isn't; the
     profile tabs lay their cards out with it. Sized by its own width, so it
     works beside the profile's side column as well as without it. -->
<template>
  <div class="profile-cards-wrap">
    <div class="profile-cards"><slot /></div>
  </div>
</template>

<style scoped>
.profile-cards-wrap {
  container-type: inline-size;
  min-width: 0;
}
.profile-cards {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 20px;
  align-items: start;
  min-width: 0;
}
@container (max-width: 560px) {
  .profile-cards {
    grid-template-columns: minmax(0, 1fr);
    gap: 16px;
  }
}
</style>
