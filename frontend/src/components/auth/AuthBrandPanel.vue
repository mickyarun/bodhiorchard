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

<!-- The navy brand panel beside the signed-out forms (sign-in, password
     change). Decorative only, so it's hidden from assistive tech. -->
<template>
  <aside class="login-brand" aria-hidden="true">
    <span class="login-brand__eyebrow">Agent-driven development</span>
    <div class="login-brand__body">
      <img :src="BRAND_MARK.dark" alt="" width="180" height="180" class="login-brand__mark" />
      <p class="login-brand__headline bo-wordmark">Glide from idea to shipped.</p>
      <p class="login-brand__lede">
        Agents handle the specs, estimates, reviews and test plans. Your team keeps the decisions.
      </p>
    </div>
    <span class="login-brand__foot">Open source · self-hosted</span>
  </aside>
</template>

<script setup lang="ts">
import { BRAND_MARK } from '@/constants/brand'
</script>

<style scoped>
.login-brand {
  min-height: 100vh;
  box-sizing: border-box;
  padding: 56px;
  display: flex;
  flex-direction: column;
  justify-content: space-between;
  gap: var(--space-xl, 3rem);
  background: var(--color-panel);
  color: var(--color-panel-ink-2);
}

.login-brand__eyebrow {
  font-size: 13px;
  font-weight: 600;
  letter-spacing: var(--tracking-label, 0.08em);
  text-transform: uppercase;
  color: var(--color-panel-accent-2);
}

.login-brand__body {
  display: flex;
  flex-direction: column;
  gap: 28px;
}

.login-brand__mark {
  width: 180px;
  height: 180px;
}

.login-brand__headline {
  margin: 0;
  max-width: 480px;
  font-size: 44px;
  line-height: 1.1;
  color: var(--color-panel-ink);
}

.login-brand__lede {
  margin: 0;
  max-width: 460px;
  font-size: 17px;
  line-height: var(--leading-body, 1.55);
}

.login-brand__foot {
  font-size: 13px;
  color: var(--color-panel-muted);
}
</style>
