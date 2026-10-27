// Copyright 2025-2026 Arun Rajkumar
//
// Licensed under the Apache License, Version 2.0 (the "License");
// you may not use this file except in compliance with the License.
// You may obtain a copy of the License at
//
//     http://www.apache.org/licenses/LICENSE-2.0
//
// Unless required by applicable law or agreed to in writing, software
// distributed under the License is distributed on an "AS IS" BASIS,
// WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
// See the License for the specific language governing permissions and
// limitations under the License.

// The current time as a ref that ticks on an interval, for relative labels
// ("3 days", overdue colouring) that must not go stale on a page left open.

import { onBeforeUnmount, ref, type Ref } from 'vue'

export function useNow(intervalMs = 60_000): Ref<Date> {
  const now = ref(new Date())
  const timer = setInterval(() => { now.value = new Date() }, intervalMs)
  onBeforeUnmount(() => clearInterval(timer))
  return now
}
